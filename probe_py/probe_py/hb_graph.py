import collections
import os
import shlex
import stat
import textwrap
import typing
import warnings
import networkx
import tqdm
from .hb_graph_accesses import hb_graph_to_accesses
from .ptypes import Inode, TaskType, Pid, ExecNo, Tid, ProbeLog, initial_exec_no, InvalidProbeLog, InodeVersion, OpQuad, HbGraph
from .ops import CloneOp, ExecOp, WaitOp, OpenOp, SpawnOp, InitExecEpochOp, InitThreadOp, Op, CloseOp, DupOp
from . import graph_utils
from . import ptypes

"""
HbGraph stands for "Happened-Before graph".

If there is an edge from operation A to operation B, then A "happened before" B.

Data *may* flow from A to B.

This can be due to program ordering or synchronization.

"""


def probe_log_to_hb_graph(probe_log: ProbeLog) -> HbGraph:
    hb_graph = HbGraph()

    _create_program_order_edges(probe_log, hb_graph)

    # Hook up synchronization edges
    for node in tqdm.tqdm(hb_graph.nodes(), "sync edges"):
        _create_clone_edges(node, probe_log, hb_graph)
        _create_exec_edges(node, probe_log, hb_graph)
        _create_spawn_edges(node, probe_log, hb_graph)
        _create_wait_edges(node, probe_log, hb_graph)

    _create_other_thread_edges(probe_log, hb_graph)

    _create_pipe_edges(probe_log, hb_graph)

    validate_hb_graph(hb_graph, True)

    return hb_graph


def retain_only(
        probe_log: ProbeLog,
        full_hb_graph: HbGraph,
        retain_node_predicate: typing.Callable[[OpQuad, Op], bool],
) -> HbGraph:
    """Retains only nodes satisfying the predicate."""
    reduced_hb_graph = HbGraph()
    last_in_process = dict[tuple[Pid, ExecNo, Tid], OpQuad]()
    incoming_to_process = dict[tuple[Pid, ExecNo, Tid], list[tuple[OpQuad, typing.Mapping[str, typing.Any]]]]()

    for node in tqdm.tqdm(
            networkx.topological_sort(full_hb_graph),
            total=len(full_hb_graph),
            desc="retain",
    ):
        node_triple = (node.pid, node.exec_no, node.tid)

        # If node satisfies predicate, copy node into new graph
        if retain_node_predicate(node, probe_log.get_op(node)):
            node_data = full_hb_graph.nodes(data=True)[node]
            reduced_hb_graph.add_node(node, **node_data)

            # Add link from previous node in this process, if any
            # Note that iteration is in topo order,
            # so this node happens-after the node of previous iterations.
            if previous_node := last_in_process.get(node_triple):
                reduced_hb_graph.add_edge(previous_node, node)
            last_in_process[node_triple] = node

            # Link up any out-of-process predecessors we accumulated up to this node
            incoming = incoming_to_process.get(node_triple, [])
            for (predecessor, edge_data) in incoming:
                reduced_hb_graph.add_edge(predecessor, node, **edge_data)
            if incoming:
                del incoming_to_process[node_triple]

        # Accumulate out-of-process predecessors
        # Since we iterate in topo order,
        # eventually nodes in the successor's process will be visisted (as "node").
        # Once we find one of those which satisfies the retain_node_predicate,
        # we will create edges from last_in_process[this node_triple] to a descendant of the successor node.
        for successor in full_hb_graph.successors(node):
            successor_triple = (successor.pid, successor.exec_no, successor.tid)
            # Note that if node_triple not in last_in_process,
            # none of the prior nodes in this process were retained,
            # so the edge doesn't synchronize any retained nodes.
            # In such case, we don't need to create an edge.
            if successor_triple != node_triple and (previous_node := last_in_process.get(node_triple)):
                edge_data = full_hb_graph.get_edge_data(node, successor)
                incoming_to_process.setdefault(successor_triple, []).append((previous_node, edge_data))

    validate_hb_graph(reduced_hb_graph, False)

    return reduced_hb_graph


def validate_hb_graph(hb_graph: HbGraph, validate_roots: bool) -> None:
    if not networkx.is_directed_acyclic_graph(hb_graph):
        cycle = list(networkx.find_cycle(hb_graph))
        raise InvalidProbeLog(f"Found a cycle in hb graph: {cycle}")

    if validate_roots:
        graph_utils.get_root(hb_graph)
        # TODO: Check that root pid and/or parent-pid is as expected.


def _create_program_order_edges(probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    if not probe_log.processes:
        raise InvalidProbeLog("No processes tracked")
    for pid, process in tqdm.tqdm(probe_log.processes.items(), "processes program order"):
        if not process.execs:
            raise InvalidProbeLog(f"No exec epochs tracked for pid {pid}")
        for exec_no, exec_epoch in process.execs.items():
            if not exec_epoch.threads:
                raise InvalidProbeLog(f"No threads tracked for exec {exec_no}")
            for tid, thread in exec_epoch.threads.items():
                if not thread.ops:
                    raise InvalidProbeLog(f"No ops tracked for thread {tid}")
                nodes = [
                    OpQuad(pid, exec_no, tid, op_no)
                    for op_no, op in enumerate(thread.ops)
                ]
                assert nodes

                hb_graph.add_nodes_from(nodes)

                # Hook up program order edges
                hb_graph.add_edges_from(zip(nodes[:-1], nodes[1:]))


def _create_clone_edges(node: OpQuad, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    op = probe_log.get_op(node)
    if isinstance(op.data, CloneOp) and op.data.ferrno == 0:
        match op.data.task_type:
            case TaskType.TASK_TID:
                target_tid = Tid(op.data.task_id)
                if target_tid not in probe_log.processes[node.pid].execs[node.exec_no].threads:
                    warnings.warn(f"Clone points to a thread {target_tid} we didn't track")
                else:
                    target = OpQuad(node.pid, node.exec_no, target_tid, 0)
                    assert hb_graph.has_node(target)
                    hb_graph.add_edge(node, target)
            case TaskType.TASK_PID:
                target_pid = Pid(op.data.task_id)
                if target_pid not in probe_log.processes:
                    warnings.warn(f"Clone points to a process {target_pid} we didn't track {probe_log.processes.keys()}")
                else:
                    target = OpQuad(target_pid, initial_exec_no, target_pid.main_thread(), 0)
                    assert hb_graph.has_node(target)
                    hb_graph.add_edge(node, target)
            case TaskType.TASK_PTHREAD | TaskType.TASK_ISO_C_THREAD:
                targets = get_first_task_nodes(probe_log, node.pid, node.exec_no, op.data.task_type, op.data.task_id, False)
                for target in targets:
                    assert hb_graph.has_node(target)
                    hb_graph.add_edge(node, target)


def get_first_task_nodes(
        probe_log: ProbeLog,
        pid: Pid,
        exec_no: ExecNo,
        task_type: int,
        task_id: int,
        reverse: bool,
) -> list[OpQuad]:
    targets = []
    for tid, thread in probe_log.processes[pid].execs[exec_no].threads.items():
        for op_no, other_op in enumerate(reversed(thread.ops) if reverse else thread.ops):
            if (task_type == TaskType.TASK_PTHREAD and other_op.pthread_id == task_id) or \
               (task_type == TaskType.TASK_ISO_C_THREAD and other_op.iso_c_thread_id == task_id):
                targets.append(OpQuad(pid, exec_no, tid, op_no))
                break
    return targets


def _create_wait_edges(node: OpQuad, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    op = probe_log.get_op(node)
    if isinstance(op.data, WaitOp) and op.data.ferrno == 0:
        match op.data.task_type:
            case TaskType.TASK_TID:
                target_tid = Tid(op.data.task_id)
                if target_tid not in probe_log.processes[node.pid].execs[node.exec_no].threads:
                    warnings.warn(f"Wait points to a thread {target_tid} we didn't track")
                else:
                    target = OpQuad(node.pid, node.exec_no, target_tid, len(probe_log.processes[node.pid].execs[node.exec_no].threads[target_tid].ops) - 1)
                    hb_graph.add_edge(target, node)
            case TaskType.TASK_PID:
                target_pid = Pid(op.data.task_id)
                if target_pid not in probe_log.processes:
                    warnings.warn(f"Wait points to a process {target_pid} we didn't track")
                else:
                    last_exec_no = max(probe_log.processes[target_pid].execs.keys())
                    last_op_no = len(probe_log.processes[target_pid].execs[last_exec_no].threads[target_pid.main_thread()].ops) - 1
                    target = OpQuad(target_pid, last_exec_no, target_pid.main_thread(), last_op_no)
                    assert hb_graph.has_node(target)
                    hb_graph.add_edge(target, node)
            case TaskType.TASK_PTHREAD | TaskType.TASK_ISO_C_THREAD:
                targets = get_first_task_nodes(probe_log, node.pid, node.exec_no, op.data.task_type, op.data.task_id, True)
                for target in targets:
                    assert hb_graph.has_node(target)
                    hb_graph.add_edge(target, node)


def _create_exec_edges(node: OpQuad, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    op = probe_log.get_op(node)
    if isinstance(op.data, ExecOp) and op.data.ferrno == 0:
        next_exec_no = node.exec_no.next()
        if next_exec_no not in probe_log.processes[node.pid].execs:
            warnings.warn(f"Exec points to an exec epoch {next_exec_no} we didn't track")
        else:
            target = OpQuad(node.pid, next_exec_no, node.pid.main_thread(), 0)
            assert hb_graph.has_node(target)
            hb_graph.add_edge(node, target)


def _create_spawn_edges(node: OpQuad, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    op = probe_log.get_op(node)
    if isinstance(op.data, SpawnOp) and op.data.ferrno == 0:
        child_pid = Pid(op.data.child_pid)
        if child_pid not in probe_log.processes:
            warnings.warn(f"Spawn points to a pid {child_pid} we didn't track")
        else:
            target = OpQuad(child_pid, initial_exec_no, child_pid.main_thread(), 0)
            assert hb_graph.has_node(target)
            hb_graph.add_edge(node, target)


def _create_other_thread_edges(probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    # Sometimes we don't have the thread creation or termination edges
    for pid, process in probe_log.processes.items():
        for exec_no, exec_epoch in process.execs.items():
            for tid, thread in exec_epoch.threads.items():
                first_op_main_thread = OpQuad(pid, exec_no, pid.main_thread(), 0)
                last_op_main_thread = OpQuad(pid, exec_no, pid.main_thread(), len(exec_epoch.threads[pid.main_thread()].ops) - 1)
                if tid != pid.main_thread():
                    first_op = OpQuad(pid, exec_no, tid, 0)
                    last_op = OpQuad(pid, exec_no, tid, len(thread.ops) - 1)
                    if len(list(hb_graph.predecessors(first_op))) == 0:
                        hb_graph.add_edge(first_op_main_thread, first_op)
                    if last_op_main_thread != first_op_main_thread and len(list(hb_graph.successors(last_op))) == 0:
                        if last_op_main_thread not in hb_graph.predecessors(last_op):
                            hb_graph.add_edge(last_op, last_op_main_thread)
                        else:
                            warnings.warn(
                                f"I want to add an edge from last op of {tid} to main thread {pid}, but that would create a cycle;"
                                f"the last op of {pid} is likely the clone that creates {tid}"
                            )


def label_nodes(probe_log: ProbeLog, hb_graph: HbGraph, add_op_no: bool = False) -> None:
    for node, data in tqdm.tqdm(hb_graph.nodes(data=True), "HBG label"):
        op = probe_log.get_op(node)
        if len(list(hb_graph.predecessors(node))) == 0:
            data["label"] = "root"
        elif isinstance(op.data, InitExecEpochOp):
            data["label"] = f"PID {node.pid} exec {node.exec_no}"
        elif isinstance(op.data, InitThreadOp):
            data["label"] = f"TID {node.tid}"
        elif isinstance(op.data, ExecOp):
            data["label"] = textwrap.fill(
                "exec " + textwrap.shorten(
                    shlex.join([
                        textwrap.shorten(
                            arg.decode(errors="backslashreplace"),
                            width=80,
                        )
                        for arg in op.data.argv
                    ]),
                    width=80 * 10,
                ),
                width=80,
            )
        elif isinstance(op.data, OpenOp):
            access = {os.O_RDONLY: "readable", os.O_WRONLY: "writable", os.O_RDWR: "read/writable"}[op.data.flags & os.O_ACCMODE]
            data["label"] = f"Open ({access}) {op.data.path.path.decode(errors='backslashreplace')}"
            data["label"] += f" fd={op.data.fd}"
            data["label"] += f"\n{InodeVersion.from_probe_path(op.data.path).inode!s}"
            data["label"] += f"\n{op.data.path.path.decode()}"
        elif isinstance(op.data, CloseOp):
            data["label"] = f"Close fd={op.data.fd}"
        elif isinstance(op.data, DupOp):
            data["label"] = f"DupOp fd={op.data.old} → fd={op.data.new}"
        else:
            data["label"] = f"{op.data.__class__.__name__}"
            data["labelfontsize"] = 8
        if getattr(op.data, "ferrno", 0) != 0:
            data["label"] += " (failed)"
            data["color"] = "red"
        if add_op_no:
            data["label"] = f"{node.op_no}: " + data["label"]

    for node0, node1, data in hb_graph.edges(data=True):
        if node0.pid != node1.pid or node0.tid != node1.tid:
            data["style"] = "dashed"

    if not networkx.is_directed_acyclic_graph(hb_graph):
        cycle = list(networkx.find_cycle(hb_graph))
        for a, b in cycle:
            hb_graph.get_edge_data(a, b)["color"] = "red"
            warnings.warn("Cycle shown in red")


def _create_pipe_edges(
        probe_log: ProbeLog,
        hb_graph: HbGraph,
) -> None:
    """
    Create an edge from the last op which could hold the write-end of a pipe or FIFO to the open op of the write end.

    Unlike ordinary files, the reader of a pipe or FIFO has a way to wait until the last writer is done
    """
    fifo_readers = collections.defaultdict[Inode, set[OpQuad]](set)
    fifo_writers = collections.defaultdict[Inode, set[OpQuad]](set)
    for access_or_op in hb_graph_to_accesses(probe_log, hb_graph):
        match access_or_op:
            case ptypes.Access():
                access = access_or_op
                print(stat.S_IFMT(access.inode.mode), access.inode)
                if stat.S_ISFIFO(access.inode.mode):
                    print(access)
                if all([
                        access.phase == ptypes.Phase.BEGIN,
                        access.mode.is_side_effect_free,
                        stat.S_ISFIFO(access.inode.mode),
                ]):
                    fifo_readers[access.inode].add(access.op_node)
                elif all([
                        access.phase == ptypes.Phase.END,
                        not access.mode.is_side_effect_free,
                        stat.S_ISFIFO(access.inode.mode),
                ]):
                    fifo_writers[access.inode].add(access.op_node)
    for fifo in fifo_readers.keys() | fifo_writers.keys():
        for writer in fifo_writers.get(fifo, set()):
            for reader in fifo_readers.get(fifo, set()):
                print(fifo, writer, reader)
                hb_graph.add_edge(writer, reader)
