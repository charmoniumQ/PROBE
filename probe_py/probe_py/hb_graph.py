from __future__ import annotations
import collections
import dataclasses
import itertools
import os
import shlex
import textwrap
import typing
import warnings
import charmonium.time_block
import networkx
from . import graph_utils
from . import ptypes
from . import ops


"""
HbGraph stands for "Happened-Before graph".

If there is an edge from operation A to operation B, then A "happened before" B.

Data *may* flow from A to B.

This can be due to program ordering or synchronization.

"""


It = collections.abc.Iterable
Map = collections.abc.Mapping


@dataclasses.dataclass(frozen=True)
class QuadRange(collections.abc.Collection[ptypes.OpQuad]):
    thread: ptypes.ThreadTriple
    start: int
    end: int

    def __contains__(self, elem: object) -> bool:
        return isinstance(elem, ptypes.OpQuad) and elem.thread_triple() == self.thread and self.start <= elem.op_no < self.end

    def __iter__(self) -> collections.abc.Iterator[ptypes.OpQuad]:
        for op_no in range(self.start, self.end):
            yield self.thread.op_quad(op_no)

    def __len__(self) -> int:
        return self.end - self.start

    @property
    def first(self) -> ptypes.OpQuad:
        return self.thread.op_quad(self.start)

    @property
    def last(self) -> ptypes.OpQuad:
        return self.thread.op_quad(self.end - 1)


class Fd(int):
    pass


class HbGraph:
    _dag: networkx.DiGraph[QuadRange]
    _quad_ranges: Map[ptypes.OpQuad, QuadRange]
    _vector_clocks: Map[QuadRange, tuple[int, ...]]

    def possible_schedule(
            self,
            start: QuadRange,
            retain_predicate: typing.Callable[[QuadRange], bool],
    ) -> collections.abc.Iterator[QuadRange]:
        traversal = graph_utils.search_with_pruning(self._dag, start)
        for quad_range in traversal:
            assert quad_range is not None
            if retain_predicate(quad_range):
                yield quad_range
                traversal.send(True)
            else:
                traversal.send(False)

    @charmonium.time_block.decor(print_start=False)
    def __init__(self, probe_log: ptypes.ProbeLog) -> None:
        self._dag = networkx.DiGraph()

        quad_ranges = _add_node_ranges(probe_log, self._dag)
        self._quad_range_map = {
            opq: range
            for range in quad_ranges
            for opq in range
        }

        pthread_to_tids = collections.defaultdict(set)
        iso_c_thread_to_tids = collections.defaultdict(set)
        for quad, op in probe_log.ops():
            pthread_to_tids[(quad.exec_pair(), op.pthread_id)].add(quad.tid)
            iso_c_thread_to_tids[(quad.exec_pair(), op.iso_c_thread_id)].add(quad.tid)

        # Hook up synchronization edges
        for quad_range in self._dag.nodes():
            quad = quad_range.last
            op = probe_log.get_op(quad)
            _create_clone_edges(quad, op, self._dag, self._quad_range_map, pthread_to_tids, iso_c_thread_to_tids)
            _create_wait_edges(quad, op, self._dag, self._quad_range_map, pthread_to_tids, iso_c_thread_to_tids, probe_log)
            _create_exec_edges(quad, op, self._dag, self._quad_range_map)
            _create_spawn_edges(quad, op, self._dag, self._quad_range_map)

        _create_other_thread_edges(probe_log, self._dag, self._quad_range_map)

        _validate_dag(probe_log, self._dag, True)

        self._vector_clocks, self._pid_to_lane, self._concurrent_pids = _make_vector_clocks(self._dag)


def _add_node_ranges(
        probe_log: ptypes.ProbeLog,
        dag: networkx.DiGraph[QuadRange],
) -> It[QuadRange]:
    """Identify ranges over which there are no sync edges

    e.g., if we return [0--2, 3--5], so there could be incoming sync edges to 0 and 3 and outoing from 2 and 5.

    It's ok to be imprecise, so there might also not happen to be sync edges at 0, 2, 3, or 5. 
    """
    ranges: list[QuadRange] = []
    for thread, thread_ops in probe_log.ops_by_thread():
        op_nos = []
        for op_no, op in enumerate(thread_ops):
            if (isinstance(
                    op.data,
                    (ops.CloneOp, ops.ExecOp, ops.ExitThreadOp),
            ) and getattr(op.data, "ferrno", 0) == 0):
                # possible outgoing sync edge
                op_nos.append(op_no + 1)
            if (isinstance(
                    op.data,
                    (ops.InitExecEpochOp, ops.InitThreadOp, ops.WaitOp),
            ) and getattr(op.data, "ferrno", 0) == 0):
                # possible ingoing sync edge
                # Check if edge is already there by coincidence
                # (if last op was an outgoing edge)
                if not op_nos or op_no != op_nos[-1]:
                    op_nos.append(op_no)
        assert op_nos[0] == 0, thread_ops[0]
        assert op_nos[-1] == len(thread_ops), thread_ops[-1]
        thread_ranges = [
            QuadRange(thread, start, end)
            for start, end in zip(op_nos[:-1], op_nos[1:])
        ]
        dag.add_nodes_from(thread_ranges)
        dag.add_edges_from(zip(thread_ranges[:-1], thread_ranges[1:]))
        ranges.extend(thread_ranges)
    return ranges


def _create_clone_edges(
        quad: ptypes.OpQuad,
        op: ops.Op,
        hb_graph: networkx.DiGraph[QuadRange],
        node_range_map: Map[ptypes.OpQuad, QuadRange],
        pthread_to_tids: Map[tuple[ptypes.ExecPair, int], It[ptypes.Tid]],
        iso_c_threads_to_tids: Map[tuple[ptypes.ExecPair, int], It[ptypes.Tid]],
) -> None:
    if isinstance(op.data, ops.CloneOp) and op.data.ferrno == 0:
        match op.data.task_type:
            case ptypes.TaskType.TASK_TID:
                targets = [quad.other_thread(ptypes.Tid(op.data.task_id), 0)]
            case ptypes.TaskType.TASK_PID:
                target_pid = ptypes.Pid(op.data.task_id)
                targets = [target_pid.exec_pair().main_thread().op_quad(0)]
            case ptypes.TaskType.TASK_PTHREAD:
                for tid in pthread_to_tids[(quad.exec_pair(), op.data.task_id)]:
                    targets = [quad.other_thread(tid, 0)]
            case ptypes.TaskType.TASK_ISO_C_THREAD:
                for tid in iso_c_threads_to_tids[(quad.exec_pair(), op.data.task_id)]:
                    targets = [quad.other_thread(tid, 0)]
        for target in targets:
            if target not in node_range_map:
                warnings.warn(ptypes.UnusualProbeLog(
                    f"Clone ({quad}) points to a tid/pid {target} we didn't track"
                ))
            else:
                # Should only connect last of range to first of range
                assert quad == node_range_map[quad].last
                assert target == node_range_map[target].first
                hb_graph.add_edge(node_range_map[quad], node_range_map[target])


def _create_wait_edges(
        quad: ptypes.OpQuad,
        op: ops.Op,
        hb_graph: networkx.DiGraph[QuadRange],
        node_range_map: Map[ptypes.OpQuad, QuadRange],
        pthread_to_tids: Map[tuple[ptypes.ExecPair, int], It[ptypes.Tid]],
        iso_c_threads_to_tids: Map[tuple[ptypes.ExecPair, int], It[ptypes.Tid]],
        probe_log: ptypes.ProbeLog,
) -> None:
    if isinstance(op.data, ops.WaitOp) and op.data.ferrno == 0:
        match op.data.task_type:
            case ptypes.TaskType.TASK_TID:
                target_threads = [quad.thread_triple().other_thread(ptypes.Tid(op.data.task_id))]
            case ptypes.TaskType.TASK_PID:
                target_pid = ptypes.Pid(op.data.task_id)
                target_threads = [ptypes.ThreadTriple(target_pid, ptypes.initial_exec_no, target_pid.main_thread())]
            case ptypes.TaskType.TASK_PTHREAD:
                for tid in pthread_to_tids[(quad.exec_pair(), op.data.task_id)]:
                    target_threads = [quad.thread_triple().other_thread(tid)]
            case ptypes.TaskType.TASK_ISO_C_THREAD:
                for tid in iso_c_threads_to_tids[(quad.exec_pair(), op.data.task_id)]:
                    target_threads = [quad.thread_triple().other_thread(tid)]
        for target_thread in target_threads:
            last_op_no = len(probe_log.processes[target_thread.pid].execs[target_thread.exec_no].threads[target_thread.tid].ops) - 1
            target_quad = target_thread.op_quad(last_op_no)
            if target_quad not in node_range_map:
                warnings.warn(ptypes.UnusualProbeLog(
                    f"Wait ({quad}) points to a tid/pid {target_thread} we didn't track"
                ))
            else:
                # Should only connect last of range to first of range
                assert quad == node_range_map[quad].first, (quad, node_range_map[quad].first)
                assert target_quad == node_range_map[target_quad].last, (target_quad, node_range_map[target_quad].last)
                hb_graph.add_edge(node_range_map[target_quad], node_range_map[quad])


def _create_exec_edges(
        quad: ptypes.OpQuad,
        op: ops.Op,
        hb_graph: networkx.DiGraph[QuadRange],
        node_range_map: Map[ptypes.OpQuad, QuadRange],
) -> None:
    if isinstance(op.data, ops.ExecOp) and op.data.ferrno == 0:
        target = quad.exec_pair().next().main_thread().op_quad(0)
        if target not in node_range_map:
            warnings.warn(ptypes.UnusualProbeLog(
                f"Exec points to an exec epoch {target} we didn't track"
            ))
        else:
            # Should only connect last of range to first of range
            assert quad == node_range_map[quad].last
            assert target == node_range_map[target].first
            hb_graph.add_edge(node_range_map[quad], node_range_map[target])


def _create_spawn_edges(
        quad: ptypes.OpQuad,
        op: ops.Op,
        hb_graph: networkx.DiGraph[QuadRange],
        node_range_map: Map[ptypes.OpQuad, QuadRange],
) -> None:
    if isinstance(op.data, ops.SpawnOp) and op.data.ferrno == 0:
        child_pid = ptypes.Pid(op.data.child_pid)
        target = child_pid.exec_pair().main_thread().op_quad(0)
        if target not in node_range_map:
            warnings.warn(ptypes.UnusualProbeLog(
                f"Spawn ({quad}) points to a pid {child_pid} we didn't track"
            ))
        else:
            # Should only connect last of range to first of range
            assert quad == node_range_map[quad].last
            assert target == node_range_map[target].first
            hb_graph.add_edge(node_range_map[quad], node_range_map[target])


def _create_other_thread_edges(
        probe_log: ptypes.ProbeLog,
        hb_graph: networkx.DiGraph[QuadRange],
        node_range_map: Map[ptypes.OpQuad, QuadRange],
) -> None:
    # Sometimes we don't have the thread creation or termination edges
    for thread, thread_ops in probe_log.ops_by_thread():
        main_thread = thread.main_thread()
        first_op_main_thread = node_range_map[main_thread.op_quad(0)]
        last_op_no = len(probe_log.processes[thread.pid].execs[thread.exec_no].threads[main_thread.tid].ops) - 1
        last_op_main_thread = node_range_map[main_thread.op_quad(last_op_no)]
        if thread.tid != thread.pid.main_thread():
            first_op = node_range_map[thread.op_quad(0)]
            last_op_no = len(probe_log.processes[thread.pid].execs[thread.exec_no].threads[thread.tid].ops) - 1
            last_op = node_range_map[thread.op_quad(last_op_no)]
            if len(list(hb_graph.predecessors(first_op))) == 0:
                hb_graph.add_edge(first_op_main_thread, first_op)
            if last_op_main_thread != first_op_main_thread and len(list(hb_graph.successors(last_op))) == 0:
                if last_op_main_thread not in hb_graph.predecessors(first_op) and not graph_utils.would_create_cycle(hb_graph, last_op, last_op_main_thread):
                    hb_graph.add_edge(last_op, last_op_main_thread)
                else:
                    warnings.warn(ptypes.UnusualProbeLog("would cycle", last_op, last_op_main_thread))


def _validate_dag(
        probe_log: ptypes.ProbeLog,
        dag: networkx.DiGraph[QuadRange],
        validate_roots: bool,
) -> None:
    if not networkx.is_directed_acyclic_graph(dag):
        cycle = list(networkx.find_cycle(dag))
        warnings.warn(ptypes.UnusualProbeLog(
            f"Found a cycle in hb graph: {cycle}",
        ))

    if validate_roots:
        sources: list[QuadRange] = graph_utils.get_sources(dag)
        if len(sources) > 1:
            warnings.warn(ptypes.UnusualProbeLog(
                f"Too many sources {sources}"
            ))
    # TODO: Check that root pid and/or parent-pid is as expected.
    # TODO: Chcek chat exec, fork, chdir are only called when exactly 1 thread is alive.


def _make_vector_clocks(
        dag: networkx.DiGraph[QuadRange],
) -> tuple[Map[QuadRange, tuple[int, ...]], Map[ptypes.Pid, int], Map[ptypes.Pid, It[ptypes.Pid]]]:
    pid_to_lane: dict[ptypes.Pid, int] = {}
    quad_range_to_clock: dict[QuadRange, tuple[int, ...]] = {}
    concurrent_pids_map = dict[ptypes.Pid, list[ptypes.Pid]]()
    current_pids = list[ptypes.Pid]()

    quad_ranges = list(networkx.topological_sort(dag))
    for quad_range in quad_ranges:
        # must be first quad_range in this pid
        if quad_range.thread.pid not in pid_to_lane:
            # assign new lane
            used_lanes = {pid_to_lane[pid] for pid in current_pids}
            all_lanes = frozenset(range(len(pid_to_lane) + 1))
            pid_to_lane[quad_range.thread.pid] = min(all_lanes - used_lanes)

            # add to current and set concurrent_pids_map[self]
            current_pids.append(quad_range.thread.pid)
            concurrent_pids_map[quad_range.thread.pid] = list(current_pids)

            # add self to concurrent_pids_map of every current process
            for process in current_pids:
                concurrent_pids_map[process].append(quad_range.thread.pid)

        # Increment the value when the lane is the same as the pred
        incremented_pred_clocks = [
            [
                value + int(lane == pid_to_lane[pred.thread.pid])
                for lane, value in enumerate(quad_range_to_clock[pred])
            ]
            for pred in dag.predecessors(quad_range)
        ]

        # max of all values in the same index for all preds
        quad_range_to_clock[quad_range] = tuple(
            max(*values)
            for values in itertools.zip_longest(
                    *incremented_pred_clocks,
                    fillvalue=0,
            )
        )

        # Must be last quad_range in this pid
        # Remove from current
        if quad_range.thread.pid not in {pred.thread.pid for pred in dag.predecessors(quad_range)}:
            current_pids.remove(quad_range.thread.pid)

    # checks
    for node0, node1 in zip(quad_ranges[:-1], quad_ranges[1:]):
        assert not quad_range_to_clock[node0] > quad_range_to_clock[node1]
    return quad_range_to_clock, pid_to_lane, concurrent_pids_map


def label_nodes(
        probe_log: ptypes.ProbeLog,
        hb_graph: networkx.DiGraph[QuadRange],
        add_op_no: bool = False,
) -> None:
    for quad_range, data in hb_graph.nodes(data=True):
        data.setdefault("label", "")
        data["cluster"] = str(quad_range.thread.pid)
        labels = []
        if len(list(hb_graph.predecessors(quad_range))) == 0:
            labels.append("root")
        for node in quad_range:
            op = probe_log.get_op(node)
            if add_op_no:
                labels.append(f"{node.op_no}:")
            if isinstance(op.data, ops.InitExecEpochOp):
                labels.append(f"PID {node.pid} exec {node.exec_no}")
            elif isinstance(op.data, ops.InitThreadOp):
                labels.append(f"TID {node.tid}")
            elif isinstance(op.data, ops.ExecOp):
                labels.append(textwrap.fill(
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
                ))
            elif isinstance(op.data, ops.OpenOp):
                access = {os.O_RDONLY: "readable", os.O_WRONLY: "writable", os.O_RDWR: "read/writable"}[op.data.flags & os.O_ACCMODE]
                labels.append(f"OpenOp ({access})  fd={op.data.fd} {ptypes.InodeVersion.from_probe_path(op.data.path).inode.number} {op.data.path.path.decode()}")
            elif isinstance(op.data, ops.StatOp):
                labels.append(f"StatOp {ptypes.InodeVersion.from_probe_path(op.data.path).inode.number} {op.data.path.path.decode()}")
            elif isinstance(op.data, ops.CloseOp):
                labels.append(f"Close fd={op.data.fd} {ptypes.InodeVersion.from_probe_path(op.data.path).inode.number} {op.data.path.path.decode()}")
            elif isinstance(op.data, ops.DupOp):
                labels.append(f"DupOp fd={op.data.old} → fd={op.data.new}")
            else:
                labels.append(f"{op.data.__class__.__name__}")
                # data["labelfontsize"] = 8
            if getattr(op.data, "ferrno", 0) != 0:
                labels[-1] = labels[-1] + " (failed)"
                # data["color"] = "red"
        data["label"] = "\n".join(labels)

    for node0, node1, edge_data in hb_graph.edges(data=True):
        if node0.thread.pid != node1.thread.pid or node0.thread.tid != node1.thread.tid:
            edge_data["style"] = "dashed"

    if not networkx.is_directed_acyclic_graph(hb_graph):
        cycle = list(networkx.find_cycle(hb_graph))
        for a, b in cycle:
            hb_graph.get_edge_data(a, b)["color"] = "red"
            warnings.warn(ptypes.UnusualProbeLog(
                "Cycle shown in red",
            ))
3
