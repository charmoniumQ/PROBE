import dataclasses
import typing
import networkx
from .ptypes import TaskType, Pid, ExecNo, Tid, ProbeLog, initial_exec_no, InvalidProbeLog
from .ops import CloneOp, ExecOp, WaitOp, SpawnOp

"""
HbGraph stands for "Happened-Before graph".

If there is an edge from operation A to operation B, then A "happened before" B.

Data *may* flow from A to B.

This can be due to program ordering or synchronization.

"""


@dataclasses.dataclass(frozen=True)
class OpNode:
    pid: Pid
    exec_no: ExecNo
    tid: Tid
    op_no: int

    def thread_triple(self) -> tuple[Pid, ExecNo, Tid]:
        return (self.pid, self.exec_no, self.tid)

    def op_quad(self) -> tuple[Pid, ExecNo, Tid, int]:
        return (self.pid, self.exec_no, self.tid, self.op_no)


if typing.TYPE_CHECKING:
    HbGraph: typing.TypeAlias = networkx.DiGraph[OpNode]
else:
    HbGraph = networkx.DiGraph


def probe_log_to_hb_graph(probe_log: ProbeLog) -> HbGraph:
    hb_graph = HbGraph()

    _create_program_order_edges(probe_log, hb_graph)
    validate_hb_graph(hb_graph, False)

    # Hook up synchronization edges
    for node in hb_graph.nodes():
        _create_exec_edges(node, probe_log, hb_graph)
        _create_spawn_edges(node, probe_log, hb_graph)
        _create_clone_edges(node, probe_log, hb_graph)
        _create_wait_edges(node, probe_log, hb_graph)
    validate_hb_graph(hb_graph, True)

    return hb_graph


def retain_only(
        full_hb_graph: HbGraph,
        retain_node_predicate: typing.Callable[[OpNode], bool],
) -> HbGraph:
    """Retains only nodes satisfying the predicate AND nodes that connect to
    other threads/execs/processes.

    The latter are needed to retain the happened-before structure.

    """
    reduced_hb_graph = HbGraph()
    last_in_process = dict[tuple[Pid, ExecNo, Tid], OpNode]()

    root = get_root(full_hb_graph)
    reduced_hb_graph.add_node(root)
    last_in_process[root.thread_triple()] = root

    for node in networkx.dfs_preorder_nodes(full_hb_graph):
        node_triple = (node.pid, node.exec_no, node.tid)
        interesting_predecessors = [
            predecessor
            for predecessor in full_hb_graph.predecessors(node)
            if (predecessor.pid, predecessor.exec_no, predecessor.tid) != node_triple
        ]
        interesting_successors = any(
            successor
            for successor in full_hb_graph.successors(node)
            if (successor.pid, successor.exec_no, successor.tid) != node_triple
        )
        if interesting_predecessors:
            for predecessor in interesting_predecessors:
                reduced_hb_graph.add_edge(predecessor, node)
            if node_triple in last_in_process:
                # NOT the first node, link to the last in process
                reduced_hb_graph.add_edge(last_in_process[node_triple], node)
            last_in_process[node_triple] = node
        elif interesting_successors:
            reduced_hb_graph.add_edge(last_in_process[node_triple], node)
            last_in_process[node_triple] = node
            # We'll add the successor edges when we come 'round to it in the pre order traversal
        elif retain_node_predicate(node):
            reduced_hb_graph.add_edge(last_in_process[node_triple], node)
            last_in_process[node_triple] = node
    return reduced_hb_graph


def get_root(hb_graph: HbGraph) -> OpNode:
    maximal_nodes = [
        node
        for node in hb_graph.nodes()
        if hb_graph.in_degree(node) == 0
    ]
    if len(maximal_nodes) != 1:
        raise InvalidProbeLog(f"No roots or too many roots: {maximal_nodes}")
    else:
        return maximal_nodes[0]


def validate_hb_graph(hb_graph: HbGraph, validate_roots: bool) -> None:
    if not networkx.is_directed_acyclic_graph(hb_graph):
        cycle = list(networkx.find_cycle(hb_graph))
        raise InvalidProbeLog(f"Found a cycle in hb graph: {cycle}")

    if validate_roots:
        get_root(hb_graph)
        # TODO: Check that root pid and/or parent-pid is as expected.


def _create_program_order_edges(probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    if not probe_log.processes:
        raise InvalidProbeLog("No processes tracked")
    for pid, process in probe_log.processes.items():
        if not process.execs:
            raise InvalidProbeLog(f"No exec epochs tracked for pid {pid}")
        for exec_no, exec_epoch in process.execs.items():
            if not exec_epoch.threads:
                raise InvalidProbeLog(f"No threads tracked for exec {exec_no}")
            for tid, thread in exec_epoch.threads.items():
                if not thread.ops:
                    raise InvalidProbeLog(f"No ops tracked for thread {tid}")
                nodes = [
                    OpNode(pid, exec_no, tid, op_no)
                    for op_no, op in enumerate(thread.ops)
                ]
                assert nodes

                # Hook up program order edges
                hb_graph.add_edges_from(zip(nodes[:-1], nodes[1:]))


def _create_clone_edges(node: OpNode, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    op = probe_log.get_op(*node.op_quad())
    if isinstance(op.data, CloneOp) and op.data.ferrno == 0:
        match op.data.task_type:
            case TaskType.TASK_TID:
                target_tid = Tid(op.data.task_id)
                if target_tid not in probe_log.processes[node.pid].execs[node.exec_no].threads:
                    raise InvalidProbeLog(f"Clone points to a thread {target_tid} we didn't track")
                hb_graph.add_edge(
                    node,
                    OpNode(node.pid, node.exec_no, target_tid, 0),
                )
            case TaskType.TASK_PID:
                target_pid = Pid(op.data.task_id)
                if target_pid not in probe_log.processes:
                    raise InvalidProbeLog(f"Clone points to a process {target_pid} we didn't track")
                hb_graph.add_edge(
                    node,
                    OpNode(target_pid, initial_exec_no, target_pid.main_thread(), 0),
                )


def _create_wait_edges(node: OpNode, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    op = probe_log.get_op(*node.op_quad())
    if isinstance(op.data, WaitOp) and op.data.ferrno == 0:
        match op.data.task_type:
            case TaskType.TASK_TID:
                target_tid = Tid(op.data.task_id)
                if target_tid not in probe_log.processes[node.pid].execs[node.exec_no].threads:
                    raise InvalidProbeLog(f"Wait points to a thread {target_tid} we didn't track")
                hb_graph.add_edge(
                    node,
                    OpNode(node.pid, node.exec_no, target_tid, -1),
                )
            case TaskType.TASK_PID:
                target_pid = Pid(op.data.task_id)
                if target_pid not in probe_log.processes:
                    raise InvalidProbeLog(f"Clone points to a process {target_pid} we didn't track")
                last_exec_no = max(probe_log.processes[target_pid].execs.keys())
                last_exec = probe_log.processes[target_pid].execs[last_exec_no]
                for tid, thread in last_exec.threads.items():
                    last_op_no = len(thread.ops) - 1
                    hb_graph.add_edge(
                        node,
                        OpNode(target_pid, last_exec_no, tid, last_op_no),
                    )


def _create_exec_edges(node: OpNode, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    op = probe_log.get_op(*node.op_quad())
    if isinstance(op.data, ExecOp) and op.data.ferrno == 0:
        next_exec_no = node.exec_no.next()
        if next_exec_no not in probe_log.processes[node.pid].execs:
            raise InvalidProbeLog(f"Exec points to an exec epoch {next_exec_no} we didn't track")
        hb_graph.add_edge(
            node,
            OpNode(node.pid, next_exec_no, node.pid.main_thread(), 0),
        )


def _create_spawn_edges(node: OpNode, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    op = probe_log.get_op(*node.op_quad())
    if isinstance(op.data, SpawnOp) and op.data.ferrno == 0:
        child_pid = Pid(op.data.child_pid)
        if child_pid not in probe_log.processes:
            raise InvalidProbeLog(f"Spawn points to a pid {child_pid} we didn't track")
        hb_graph.add_edge(
            node,
            OpNode(child_pid, initial_exec_no, child_pid.main_thread(), 0),
        )
