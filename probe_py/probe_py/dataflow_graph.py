from __future__ import annotations
import collections
import dataclasses
import datetime
import enum
import itertools
import os
import pathlib
import re
import textwrap
import typing
import warnings
import charmonium.time_block
import frozendict
import networkx
import tqdm
from . import graph_utils
from . import hb_graph
from . import ops
from . import ptypes
from . import util


@dataclasses.dataclass(frozen=True)
class InodeVersionNode:
    """A particular version of the inode"""
    inode: ptypes.Inode
    version: int
    deduplicator: int | None = None

    def __str__(self) -> str:
        return f"{self.inode} version {self.version}"


It: typing.TypeAlias = collections.abc.Iterable
Map: typing.TypeAlias = collections.abc.Mapping
Seq: typing.TypeAlias = collections.abc.Sequence
T_co = typing.TypeVar("T_co", covariant=True)
V_co = typing.TypeVar("V_co", covariant=True)
FrozenDict: typing.TypeAlias = frozendict.frozendict[T_co, V_co]
NodeData: typing.TypeAlias = dict[str, typing.Any]


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuad | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[networkx.DiGraph[ptypes.OpQuad] | tuple[InodeVersionNode, ...]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph


@charmonium.time_block.decor(print_start=False)
def hb_graph_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
) -> tuple[
    CompressedDataflowGraph,
    Map[ptypes.Inode, It[pathlib.Path]],
    ptypes.HbGraph,
    graph_utils.ReachabilityOracle[ptypes.OpQuad],
]:
    # Find the HBG
    hbg = hb_graph.probe_log_to_hb_graph(probe_log)

    # Remove unnecessary nodes
    hbg = hb_graph.retain_only(probe_log, hbg, _is_interesting_for_dataflow)

    # DFG starts out with HBG
    # All HBG edges (program order, fork, join, exec) are also dataflow edges
    # But there are some dataflow edges/nodes that are not HB edges/nodes (e.g., inodes and edges-to/from-inodes).
    # We will add those next.
    dataflow_graph = typing.cast(
        DataflowGraph,
        hbg.copy(),
    )

    # We will need an HB oracle on this to evaluate transitive reachability
    hb_oracle = graph_utils.PrecomputedReachabilityOracle[ptypes.OpQuad].create(hbg)

    # For each inode, find the interval in which it was accessed
    inode_intervals, inode_to_paths = find_intervals(probe_log, hbg, hb_oracle)

    # For each inode
    for inode, interval_infos in tqdm.tqdm(inode_intervals.items(), desc="Add intervals for inode to graph"):
        add_inode_intervals(inode, interval_infos, dataflow_graph)
        # TODO: Check these with the recorded mtime

    # Add DFG edges for threads
    add_thread_dataflow_edges(hbg, hb_oracle, dataflow_graph)
    # TODO: More generally, create DFG edges for all nodes that have implicit communication (e.g., threads, network connections)
    # For each node in the set of nodes sharing memory,
    #     Find the earliest peer nodes.
    # For each node:
    #     For each node that I am a peer but my successor isn't,
    #         Add edge from self to that node

    # TODO: We should return a map from path to inode and inode to IVLs
    # These maps facilitate "does A depend on B?" queries.

    compressed_dataflow_graph = typing.cast(
        CompressedDataflowGraph,
        graph_utils.map_nodes(
            lambda node: (
                graph_utils.create_digraph([node], []) if isinstance(node, ptypes.OpQuad) else
                (node,) if isinstance(node, InodeVersionNode) else
                util.raise_(TypeError(node, type(node)))
            ),
            dataflow_graph,
            check=True,
        )
    )
    # Make dfg have the same datatype as a compressed graph

    return compressed_dataflow_graph, inode_to_paths, hbg, hb_oracle


@charmonium.time_block.decor(print_start=False)
def hb_graph_to_dataflow_graph_simple(
        probe_log: ptypes.ProbeLog,
) -> tuple[
    CompressedDataflowGraph,
    Map[ptypes.Inode, It[pathlib.Path]],
    ptypes.HbGraph,
    graph_utils.ReachabilityOracle[ptypes.OpQuad] | None,
]:
    # Find the HBG
    hbg = hb_graph.probe_log_to_hb_graph(probe_log)

    # Remove unnecessary nodes
    hbg = hb_graph.retain_only(probe_log, hbg, _is_interesting_for_dataflow)


    dataflow_graph: DataflowGraph = networkx.DiGraph()

    ee_to_init = {}
    for quad in hbg.nodes():
        op_data = probe_log.get_op(quad).data
        if isinstance(op_data, ops.InitExecEpochOp):
            ee_to_init[quad.exec_pair()] = quad

    inode_versions: dict[ptypes.Inode, int] = {}
    inode_to_paths = collections.defaultdict[ptypes.Inode, list[pathlib.Path]](list)
    cwds = dict[ptypes.Pid, pathlib.Path]()

    for quad in networkx.topological_sort(hbg):
        op_data = probe_log.get_op(quad).data
        match op_data:
            case ops.InitExecEpochOp():
                cwds[quad.pid] = _to_path(cwds, inode_to_paths, quad, op_data.cwd)
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.exe)
                inode_to_paths[inode_version.inode].append(_to_path(cwds, inode_to_paths, quad, op_data.exe))
            case ops.OpenOp():
                inode = ptypes.InodeVersion.from_probe_path(op_data.path).inode
                access = ptypes.AccessMode.from_open_flags(op_data.flags)
                if access.is_read:
                    version = inode_versions.get(inode, -1)
                    ivl = InodeVersionNode(inode, version)
                    dataflow_graph.add_edge(ivl, ee_to_init[quad.exec_pair()])
                if access.is_write:
                    old_version = inode_versions.get(inode, -1)
                    new_version = old_version + 1
                    new_ivl = InodeVersionNode(inode, version + 1)
                    if access.is_mutating_write:
                        old_ivl = InodeVersionNode(inode, version)
                        dataflow_graph.add_edge(old_ivl, new_ivl)
                    dataflow_graph.add_edge(ee_to_init[quad.exec_pair()], new_ivl)
                    inode_versions[inode] = new_version
                    path = _to_path(cwds, inode_to_paths, quad, op_data.path)
                    inode_to_paths[inode].append(path)
            case ops.ChdirOp():
                cwds[quad.pid] = _to_path(cwds, inode_to_paths, quad, op_data.path)
            case ops.CloneOp():
                if op_data.task_type == ptypes.TaskType.TASK_PID:
                    dataflow_graph.add_edge(
                        ee_to_init[quad.exec_pair()],
                        ee_to_init[ptypes.ExecPair(ptypes.Pid(op_data.task_id), ptypes.ExecNo(0))],
                    )
            case ops.ExecOp():
                dataflow_graph.add_edge(
                    ee_to_init[quad.exec_pair()],
                    ee_to_init[ptypes.ExecPair(quad.pid, quad.exec_no + 1)],
                )

    compressed_dataflow_graph = typing.cast(
        CompressedDataflowGraph,
        graph_utils.map_nodes(
            lambda node: (
                graph_utils.create_digraph([node], []) if isinstance(node, ptypes.OpQuad) else
                (node,) if isinstance(node, InodeVersionNode) else
                util.raise_(TypeError(node, type(node)))
            ),
            dataflow_graph,
            check=True,
        )
    )
    # Make dfg have the same datatype as a compressed graph

    return compressed_dataflow_graph, inode_to_paths, hbg, None


def compress_dataflow_graph(
        dataflow_graph: CompressedDataflowGraph,
        ignore_paths: Seq[pathlib.Path | re.Pattern[str]],
        contract_processes: bool,
        maximum_merge_ambiguity: int,
) -> CompressedDataflowGraph:
    warnings.warn("Compression not implemented yet") # FIXME
    return dataflow_graph


def visualize_dataflow_graph(
        dfg: CompressedDataflowGraph,
        inode_to_paths: Map[ptypes.Inode, It[pathlib.Path]],
        ignore_paths: Seq[pathlib.Path | re.Pattern[str]],
        relative_to: pathlib.Path,
        probe_log: ptypes.ProbeLog,
) -> CompressedDataflowGraph:
    dfg2 = filter_paths(dfg, inode_to_paths, ignore_paths)
    label_nodes(
        probe_log,
        dfg2,
        inode_to_paths,
        relative_to=relative_to,
    )
    return dfg2


@dataclasses.dataclass(frozen=True)
class ProcessState:
    pid: ptypes.Pid
    epoch_no: ptypes.ExecNo
    deduplicator: int


@dataclasses.dataclass(frozen=True)
class IntervalsPerProcess:
    intervals: FrozenDict[ptypes.Pid, graph_utils.Interval[ptypes.OpQuad]]

    def all_greater_than(self, other: IntervalsPerProcess) -> bool:
        return all(
            pid in self.intervals and self.intervals[pid].all_greater_than(other_interval)
            for pid, other_interval in other.intervals.items()
        )

    def __bool__(self) -> bool:
        "Whether any of the intervals are non-empty"
        return any(self.intervals.values())

    @staticmethod
    def singleton(
            hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
            quad: ptypes.OpQuad,
    ) -> IntervalsPerProcess:
        return IntervalsPerProcess(FrozenDict[ptypes.Pid, graph_utils.Interval[ptypes.OpQuad]]({quad.pid: graph_utils.Interval.singleton(hb_oracle, quad)}))

    @staticmethod
    def union(*intervals_per_processs: IntervalsPerProcess) -> IntervalsPerProcess:
        union_intervals_per_process = {}
        for intervals_per_process in intervals_per_processs:
            for process, interval in intervals_per_process.intervals.items():
                if process not in union_intervals_per_process:
                    union_intervals_per_process[process] = interval
                else:
                    union_intervals_per_process[process] = graph_utils.Interval.union(
                        union_intervals_per_process[process], interval,
                    )
        return IntervalsPerProcess(FrozenDict[ptypes.Pid, graph_utils.Interval[ptypes.OpQuad]](union_intervals_per_process))


@dataclasses.dataclass(frozen=True)
class IntervalInfo:
    access_mode: ptypes.AccessMode
    inode_version: ptypes.InodeVersion
    intervals: IntervalsPerProcess

    # TODO: Make this graph general
    # We currently assume the ndoes are structured into processes.
    # But this algorithm should work however the nodes are structured.
    # Especially since two processes may implicitly share information with network or mmap.

    def top(self) -> It[ptypes.OpQuad]:
        for interval in self.intervals.intervals.values():
            yield from interval.upper_bound

    def bottom(self) -> It[ptypes.OpQuad]:
        for interval in self.intervals.intervals.values():
            yield from interval.lower_bound


def _is_interesting_for_dataflow(node: ptypes.OpQuad, op: ops.Op) -> bool:
    return isinstance(
        op.data,
        (ops.OpenOp, ops.CloseOp, ops.CloneOp, ops.DupOp, ops.ExecOp, ops.ChdirOp, ops.InitExecEpochOp, ops.WaitOp, ops.MkFileOp),
    ) and getattr(op.data, "ferrno", 0) == 0


def _score_children(parent: ptypes.OpQuad, child: ptypes.OpQuad) -> int:
    return 0 if parent.tid == child.tid else 1 if parent.pid == child.pid else 2 if parent.pid <= child.pid else 3


def _to_path(
        cwds: Map[ptypes.Pid, pathlib.Path],
        inode_to_paths: Map[ptypes.Inode, Seq[pathlib.Path]],
        quad: ptypes.OpQuad,
        path: ops.Path,
) -> pathlib.Path:
    inode = ptypes.InodeVersion.from_probe_path(path).inode
    if path.path:
        path_arg = pathlib.Path(path.path.decode())
        if quad.pid in cwds:
            return cwds[quad.pid] / path_arg
        elif path_arg.is_absolute():
            return path_arg
        else:
            warnings.warn(ptypes.UnusualProbeLog(f"Unkonwn cwd at quad {quad}; Did we not see InitExecEpoch?"))
            return pathlib.Path()
    elif inode in inode_to_paths:
        return inode_to_paths[inode][-1]
    else:
        print(ptypes.UnusualProbeLog(f"Unkonwn path for {inode} at quad {quad}"))
        return pathlib.Path()


def find_intervals(
        probe_log: ptypes.ProbeLog,
        hb_graph: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
) -> tuple[Map[ptypes.Inode, Seq[IntervalInfo]], Map[ptypes.Inode, Seq[pathlib.Path]]]:
    inode_to_intervals = collections.defaultdict[ptypes.Inode, list[IntervalInfo]](list)
    cwds = dict[ptypes.Pid, pathlib.Path]()
    inode_to_paths = collections.defaultdict[ptypes.Inode, list[pathlib.Path]](list)

    quads = graph_utils.topological_sort_depth_first(hb_graph, score_children=_score_children)
    for quad in tqdm.tqdm(quads, total=len(hb_graph), desc="Ops -> intervals"):
        assert quad is not None
        op_data = probe_log.get_op(quad).data
        match op_data:
            case ops.InitExecEpochOp():
                cwds[quad.pid] = _to_path(cwds, inode_to_paths, quad, op_data.cwd)
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.exe)
                interval = IntervalsPerProcess.singleton(hb_oracle, quad)
                inode_to_intervals[inode_version.inode].append(IntervalInfo(ptypes.AccessMode.EXEC, inode_version, interval))
                inode_to_paths[inode_version.inode].append(_to_path(cwds, inode_to_paths, quad, op_data.exe))
            case ops.ChdirOp():
                cwds[quad.pid] = _to_path(cwds, inode_to_paths, quad, op_data.path)
            case ops.MkFileOp():
                if op_data.file_type == ptypes.FileType.PIPE.value:
                    inode = ptypes.InodeVersion.from_probe_path(op_data.path).inode
                    inode_to_paths[inode] = [pathlib.Path("/[pipe]")]
            case ops.OpenOp():
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.path)
                interval = find_closes(
                    probe_log,
                    hb_graph,
                    hb_oracle,
                    quad,
                    op_data.fd,
                    bool(op_data.flags & os.O_CLOEXEC),
                    inode_version,
                )
                access = ptypes.AccessMode.from_open_flags(op_data.flags)
                inode_to_intervals[inode_version.inode].append(IntervalInfo(access, inode_version, interval))
                path = _to_path(cwds, inode_to_paths, quad, op_data.path)
                inode_to_paths[inode_version.inode].append(path)
        assert quads.send(True) is None
    return inode_to_intervals, inode_to_paths


def find_closes(
        probe_log: ptypes.ProbeLog,
        hb_graph: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        initial_quad: ptypes.OpQuad,
        initial_fd: int,
        initial_cloexec: bool,
        inode_version: ptypes.InodeVersion,
) -> IntervalsPerProcess:
    fds_to_watch = collections.defaultdict[ptypes.Pid, set[int]](set)
    fds_to_watch[initial_quad.pid].add(initial_fd)
    cloexecs = {initial_quad.pid: {initial_fd: initial_cloexec}}
    opens = collections.defaultdict(set, {initial_quad.pid: {initial_quad}})
    closes = collections.defaultdict(set)
    quads = graph_utils.topological_sort_depth_first(
        hb_graph,
        initial_quad,
        _score_children,
        hb_oracle,
    )
    # Iterate past the initial quad
    assert quads.send(None) == initial_quad
    assert quads.send(True) is None
    print(f"  Searching for {fds_to_watch} {inode_version.inode}")
    start = datetime.datetime.now()

    for i, quad in enumerate(quads):
        assert quad is not None
        assert hb_oracle.is_reachable(initial_quad, quad)
        op_data = probe_log.get_op(quad).data
        print(f"    {quad} {op_data.__class__.__name__}, {fds_to_watch}")
        match op_data:
            case ops.OpenOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    print(f"    Subsequent open of a different {op_data.fd} pruned")
                    assert quads.send(False) is None
                    continue
            case ops.ExecOp():
                for fd in list(fds_to_watch[quad.pid]):
                    if cloexecs[quad.pid][fd]:
                        print(f"    Cloexec {fd}")
                        fds_to_watch[quad.pid].remove(fd)
                        if not fds_to_watch[quad.pid]:
                            closes[quad.pid].add(quad)
            case ops.CloseOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    print(f"    Close {op_data.fd}")
                    fds_to_watch[quad.pid].remove(op_data.fd)
                    if not fds_to_watch[quad.pid]:
                        closes[quad.pid].add(quad)
                else:
                    pass
                    print(f"    Close {op_data.fd} (unrelated)")
            case ops.DupOp():
                if op_data.old in fds_to_watch[quad.pid]:
                    fds_to_watch[quad.pid].add(op_data.new)
                    cloexecs[quad.pid][op_data.new] = bool(op_data.flags & os.O_CLOEXEC)
                    print(f"    Dup {op_data.old} -> {op_data.new} {fds_to_watch}")
            case ops.CloneOp():
                if op_data.task_type == ptypes.TaskType.TASK_PID:
                    target = ptypes.Pid(op_data.task_id)
                    if fds_to_watch[quad.pid]:
                        opens[target].add(ptypes.OpQuad(target, ptypes.initial_exec_no, target.main_thread(), 0))
                    print("    Clone")
                    if op_data.flags & os.CLONE_FILES:
                        fds_to_watch[target] = fds_to_watch[quad.pid]
                        cloexecs[target] = cloexecs[quad.pid]
                    else:
                        fds_to_watch[target] = {*fds_to_watch[quad.pid]}
                        cloexecs[target] = {**cloexecs[quad.pid]}
            # TODO: PosixSpawnOp

        if not any(
            successor.pid == quad.pid
            for successor in hb_graph.successors(quad)
        ):
            print("  Last quad in this process; autoclosing")
            closes[quad.pid].add(quad)
            fds_to_watch[quad.pid].clear()

        if not fds_to_watch[quad.pid]:
            print(f"  No more FDs to watch in {quad.pid}")
            assert quads.send(False) is None
        else:
            assert quads.send(True) is None

        fds_to_watch = collections.defaultdict(set, {
            pid: fds
            for pid, fds in fds_to_watch.items()
            if fds
        })

    if any(fds_to_watch.values()):
        warnings.warn(ptypes.UnusualProbeLog(
            f"We don't know where {fds_to_watch} got closed."
        ))
        for pid, fds in fds_to_watch.items():
            if fds:
                last_exec_no = max(probe_log.processes[pid].execs.keys())
                _, last_quad = _get_first_and_last_quad(hb_graph, pid, last_exec_no)
                closes[pid].add(last_quad)

    assert opens.keys() == closes.keys()

    startpoints = sum(map(len, opens.values()))
    endpoints = sum(map(len, closes.values()))
    n_proc = len(opens.keys())

    end = datetime.datetime.now()
    duration = end - start
    if duration > datetime.timedelta(seconds=0.1):
        print(f"find_closes: {{{startpoints} startpoints}}->{{{endpoints} endpoints}} across {n_proc} processes, passing {i} quads in {duration.total_seconds():.1f}sec")
    start = end

    start = datetime.datetime.now()
    ret = IntervalsPerProcess(FrozenDict[ptypes.Pid, graph_utils.Interval[ptypes.OpQuad]]({
        pid: graph_utils.Interval(hb_oracle, frozenset(opens[pid]), frozenset(closes[pid]))
        for pid in opens.keys()
    }))
    end = datetime.datetime.now()
    duration = end - start
    if duration > datetime.timedelta(seconds=0.1):
        print(f"find_closes: Build {n_proc} interval union in {duration.total_seconds():.1f}")
    return ret


def add_thread_dataflow_edges_old(
    hb_graph: ptypes.HbGraph,
    hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
    dataflow_graph: DataflowGraph,
) -> None:
    # For all threads, every op in this thread can dataflow to every op in each sibling thread that does not happen before it.
    # We only need to add an edge to the first op in each sibling thread that does not happen before it.
    # We only need to do this for ops just before the ops in this thread that happen-after an op in the other thread.

    thread_to_ops = collections.defaultdict(set)
    for quad in dataflow_graph.nodes():
        if isinstance(quad, ptypes.OpQuad):
            thread_to_ops[quad.thread_triple()].add(quad)
    thread_to_ops_sorted = {
        thread_triple: sorted(thread_quads, key=lambda quad: quad.op_no)
        for thread_triple, thread_quads in thread_to_ops.items()
    }
    del thread_to_ops # only use sorted from now on.

    threads_to_siblings = collections.defaultdict(set)
    for thread_triple in thread_to_ops_sorted.keys():
        threads_to_siblings[thread_triple.exec_pair()].add(thread_triple)

    # Actually add the edges
    for thread_siblings in threads_to_siblings.values():
        for src_thread, dst_thread in itertools.permutations(thread_siblings, 2):
            add_thread_siblings_dataflow_edges(
                thread_to_ops_sorted[src_thread],
                thread_to_ops_sorted[dst_thread],
                hb_oracle,
                dataflow_graph,
            )


def add_thread_dataflow_edges(
    hb_graph: ptypes.HbGraph,
    hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
    dataflow_graph: DataflowGraph,
) -> None:
    # For all threads, every op in this thread can dataflow to every op in each sibling thread that does not happen before it.
    # We only need to add an edge to the first op in each sibling thread that does not happen before it.
    # We only need to do this for ops just before the ops in this thread that happen-after an op in the other thread.

    exec_pair_to_quads = collections.defaultdict(set)
    for quad in dataflow_graph.nodes():
        if isinstance(quad, ptypes.OpQuad):
            exec_pair_to_quads[quad.exec_pair()].add(quad)
    topo_sort = networkx.topological_sort(hb_graph)
    topo_ordering = {
        node: idx
        for idx, node in enumerate(topo_sort)
    }
    for implicitly_communicating_quads in exec_pair_to_quads.values():
        connect_implicit_communication(
            list(implicitly_communicating_quads),
            topo_ordering,
            dataflow_graph,
            hb_graph,
            hb_oracle,
        )


def connect_implicit_communication(
        quads: Seq[ptypes.OpQuad],
        topo_ordering: Map[ptypes.OpQuad, int],
        dataflow_graph: DataflowGraph,
        hb: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
) -> None:
    quads = sorted(
        quads,
        key=topo_ordering.get, # type: ignore
    )
    highest_peers = dict[ptypes.OpQuad, set[ptypes.OpQuad]]()
    for src in quads:
        highest_peers[src] = set()
        for potential_highest_peer in quads:
            # This is N^2 with the number of quads in a 
            if src != potential_highest_peer and hb_oracle.is_peer(src, potential_highest_peer):
                if not any(hb_oracle.is_reachable(highest_peer, potential_highest_peer) for highest_peer in highest_peers[src]):
                    highest_peers[src].add(potential_highest_peer)
    for src in quads[::-1]:
        successors_peers = set()
        for successor in hb.predecessors(src):
            if successor in highest_peers:
                successors_peers.update(highest_peers[successor])
        for peer in highest_peers[src] - successors_peers:
            dataflow_graph.add_edge(src, peer, style="dotted")


def add_thread_siblings_dataflow_edges(
        src_ops: Seq[ptypes.OpQuad],
        dst_ops: Seq[ptypes.OpQuad],
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
) -> None:
    def dst_before_src(dst_idx: int, src_idx: int) -> bool:
        return hb_oracle.is_reachable(dst_ops[dst_idx], src_ops[src_idx])

    assert src_ops # has zeroth element

    src_index = 0
    for dst_index in range(len(dst_ops) - 1, -1, -1):
        if not dst_before_src(dst_index, src_index):
            earliest_dst_not_before_src = dst_index
            assert dst_before_src(earliest_dst_not_before_src - 1, src_index), (earliest_dst_not_before_src, src_index)
            assert not dst_before_src(earliest_dst_not_before_src, src_index), (earliest_dst_not_before_src, src_index)
            del dst_index
            break
    else:
        # No hb edge from dst -> src.
        # All of src (last node) could happen before all fo dst (first node)
        dataflow_graph.add_edge(src_ops[-1], dst_ops[0])
        return

    while True:
        latest_dst_before_src = earliest_dst_not_before_src - 1
        assert dst_before_src(latest_dst_before_src, src_index)
        assert not dst_before_src(earliest_dst_not_before_src, src_index)
        for src_index in range(src_index + 1, len(src_ops)):
            if dst_before_src(earliest_dst_not_before_src, src_index):
                latest_src_not_after_ednbs = src_index - 1
                earliest_src_after_ednbs = src_index
                del src_index
        else:
            # no src op is after earliest_dst_not_before_src
            dataflow_graph.add_edge(src_ops[-1], dst_ops[earliest_dst_not_before_src])

        assert not dst_before_src(earliest_dst_not_before_src, latest_src_not_after_ednbs)
        assert dst_before_src(earliest_dst_not_before_src, earliest_src_after_ednbs)
        dataflow_graph.add_edge(
            src_ops[latest_src_not_after_ednbs],
            dst_ops[earliest_dst_not_before_src],
        )

        dst_index = earliest_dst_not_before_src
        src_index = earliest_src_after_ednbs
        assert dst_before_src(dst_index, src_index)
        # At this point, variables shuffle around, so variables are not quite accurate anymore.
        # Delete the inaccurate names
        del latest_dst_before_src, earliest_dst_not_before_src, latest_src_not_after_ednbs, earliest_src_after_ednbs

        for dst_index in range(dst_index + 1, len(dst_ops)):
            if not dst_before_src(dst_index, src_index):
                earliest_dst_not_before_src = dst_index
                assert dst_before_src(earliest_dst_not_before_src - 1, src_index)
                del dst_index
                break
        else:
            # dst_index -> src_index, but never dst_index -> future_src_index
            # No edge can be added from src_thread to dst_thrad
            return


def add_inode_intervals(
        inode: ptypes.Inode,
        intervals: It[IntervalInfo],
        dataflow_graph: DataflowGraph,
) -> None:
    # Let W := all intervals (not intervals_per_process) in which inode was written
    # Likewise, R := was read. Read-write?
    # Let G be the dag induced by the partial order of U union W based on the relation(a, b):
    # all of the last of a happen before any of the first of b.
    # While a and b are within one pid, they may be in different threads, and may have multiple firsts and lasts.
    # G2 := transitive reduction of G
    # The w->r edges of G2 become "major versions".
    # Reads will see the major version emenating from dominating, ancestral Ws (Ws that are not after another ancestral W).
    # But for each pair of write and read, we will introduce an "intermediate versions" if last of w do not all happen-before any of the first of r.
    # For every interval, either A is completely first, B is completely first, or idk. The former become edges, the middle anti-edges, and the latter, intermediate versions.
    # Even when neither happens before the other, still some sub-sequences may happen-before other sub-sequences.
    # That is a refinement for later.

    # Construct partial order DAG on intervals.

    # FIXME: add_nodes_from
    interval_hb: networkx.DiGraph[IntervalInfo] = graph_utils.create_digraph(
        intervals,
        [
            (s0, s1)
            for s0, s1 in itertools.permutations(intervals, 2)
            if s0.intervals.all_greater_than(s1.intervals)
        ]
    )

    # Use the transitive closure to eliminate unnecessary edges (makes versions more precise)
    # Suppose A, B, and C are read/writes where A before B, B before C, and A before C, what version does C see?
    # A and B happen before C, but it would only see B, because B happens "more closely before"; i.e., A -> B -> C.
    # This is equivalent to the transitive reduction.
    interval_hb = networkx.transitive_reduction(interval_hb)

    # Construct the hb oracle, which will help us know the peer and reachable nodes
    interval_hb_oracle = graph_utils.PrecomputedReachabilityOracle.create(interval_hb)

    for interval in intervals:
        if interval.access_mode.is_write:
            write_interval = interval

            # TODO: properly version IVLs
            ivl = InodeVersionNode(inode, hash(write_interval) ^ hash(inode))
            dataflow_graph.add_node(
                ivl
            )
            for node in write_interval.top():
                dataflow_graph.add_edge(node, ivl)
                if not write_interval.access_mode.is_mutating_write:
                    # Mutating write, e.g., "replace the 100th byte with 23".
                    # The _process_ can't be influened by the current contents of the ivl,
                    # But the outputted version _is_ influenced by the current version of the ivl.
                    # Do same logic as read, but hook up to ivl instead of to process.
                    # See `if interval.access_mode.is_read` section for details.

                    # Transient versions
                    concurrent_writes = get_concurrent_writes(write_interval, interval_hb, interval_hb_oracle)
                    for pred_write_interval in concurrent_writes:
                        pred_ivl = InodeVersionNode(inode, hash(write_interval) ^ hash(pred_write_interval) ^ hash(inode))
                        dataflow_graph.add_node(pred_ivl)
                        for node in write_interval.bottom():
                            dataflow_graph.add_edge(pred_ivl, ivl)
                    # Non-transient versions
                    preceeding_writes = get_latest_preceeding_writes(write_interval, interval_hb, interval_hb_oracle)
                    for pred_write_interval in preceeding_writes:
                        pred_ivl = InodeVersionNode(inode, hash(pred_write_interval) ^ hash(inode))
                        dataflow_graph.add_edge(pred_ivl, ivl)

                    # If no preceeding writes, we pick up whatever version existed prior to execution
                    if not preceeding_writes:
                        pred_ivl = InodeVersionNode(inode, hash(write_interval) ^ hash(inode) ^ hash("pre-existing"))
                        dataflow_graph.add_node(pred_ivl)
                        dataflow_graph.add_edge(pred_ivl, ivl)

        if interval.access_mode.is_read:
            read_interval = interval

            # If a read and a write are concurrent,
            # the read can access the version produced while the write is in progress.
            # That version _might_ not be accessed by any other reader.
            # It's a version unique to the reader-writer pair, aka "transient version".
            concurrent_writes = get_concurrent_writes(read_interval, interval_hb, interval_hb_oracle)
            for write_interval in concurrent_writes:
                ivl = InodeVersionNode(inode, hash(read_interval) ^ hash(write_interval) ^ hash(inode))
                dataflow_graph.add_node(ivl)
                for node in write_interval.bottom():
                    dataflow_graph.add_edge(node, ivl)
                for node in read_interval.top():
                    dataflow_graph.add_edge(ivl, node)

            # Hook up the existing, non-transient version of each immediately preceeding write interval
            # "Immediately prceeding" but ignoring reads,
            # E.g., "write -> read -> read"; the write's version is used for both reads.
            preceeding_writes = get_latest_preceeding_writes(read_interval, interval_hb, interval_hb_oracle)
            for write_interval in preceeding_writes:
                ivl = InodeVersionNode(inode, hash(read_interval) ^ hash(inode))
                for node in read_interval.top():
                    dataflow_graph.add_edge(ivl, node)

            # If no preceeding writes, we pick up whatever version existed prior to execution
            if not preceeding_writes:
                ivl = InodeVersionNode(inode, hash(read_interval) ^ hash(inode) ^ hash("pre-existing"))
                dataflow_graph.add_node(ivl)
                for node in read_interval.top():
                    dataflow_graph.add_edge(ivl, node)


def get_concurrent_writes(
        interval: IntervalInfo,
        interval_hb: networkx.DiGraph[IntervalInfo],
        interval_hb_oracle: graph_utils.ReachabilityOracle[IntervalInfo],
) -> It[IntervalInfo]:
    for other_interval in interval_hb.nodes():
        if other_interval != interval and other_interval.access_mode.is_write and interval_hb_oracle.is_peer(other_interval, interval):
            yield other_interval


def get_latest_preceeding_writes(
        interval: IntervalInfo,
        interval_hb: networkx.DiGraph[IntervalInfo],
        interval_hb_oracle: graph_utils.ReachabilityOracle[IntervalInfo],
) -> It[IntervalInfo]:
    preceeding_write_intervals = []
    for other_interval in interval_hb.nodes():
        if other_interval.access_mode.is_write and interval_hb_oracle.is_reachable(other_interval, interval):
            preceeding_write_intervals.append(other_interval)
    return interval_hb_oracle.get_bottommost(preceeding_write_intervals)


@charmonium.time_block.decor(print_start=False)
def combine_indistinguishable_inodes(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
    # FIXME: Make the elimination optional at a CLI level
    # Note the type still has to be converted from DataflowGraph to CompressedDataflowGraph

    sccs = list(networkx.strongly_connected_components(dataflow_graph))
    scc_lens = sorted([len(scc) for scc in sccs], reverse=True)
    scc_total = sum(scc_lens)
    print(f"{len(sccs)} sccs with nodes {scc_lens[:5]} (total {scc_total})")

    n_ops = sum(
        isinstance(node, ptypes.OpQuad)
        for node in dataflow_graph.nodes()
    )
    with charmonium.time_block.ctx("combine adjacent ops", print_start=False):
        dataflow_graph2 = combine_adjacent_ops(probe_log, hbg, hb_oracle, dataflow_graph)
    n_ops2 = sum(
        isinstance(node, ProcessState)
        for node in dataflow_graph2.nodes()
    )
    print(f"Combined adjacent ops {n_ops} -> {n_ops2}")
    n_inodes = sum(
        isinstance(node, InodeVersionNode)
        for node in dataflow_graph2.nodes()
    )
    with charmonium.time_block.ctx("combine similar equivalent inodes", print_start=False):
        dataflow_graph3 = graph_utils.combine_twin_nodes(
            dataflow_graph2,
            lambda node: isinstance(node, InodeVersionNode),
        )
        # dataflow_graph3 = graph_utils.map_nodes(
        #     lambda node: node if isinstance(node, ProcessState) else frozenset({node}),
        #     dataflow_graph2
        # )
    n_inodes2 = sum(
        isinstance(node, frozenset)
        for node in dataflow_graph3.nodes()
    )
    print(f"Combined isomorphic inodes {n_inodes} -> {n_inodes2}")
    # n_edges = len(dataflow_graph.edges())
    # with charmonium.time_block.ctx("transitive reduction", print_start=False):
    #     dataflow_graph4 = graph_utils.transitive_reduction_cyclic_graph(dataflow_graph3)
    # n_edges2 = len(dataflow_graph4.edges())
    #print(f"Transitive reduction {n_edges} -> {n_edges2}")
    return typing.cast(CompressedDataflowGraph, dataflow_graph3)


def combine_adjacent_ops(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
) -> networkx.DiGraph[ProcessState | InodeVersionNode]:
    for node in dataflow_graph:
        if isinstance(node, ptypes.OpQuad):
            assert node in hb_oracle
    for node in hbg:
        assert node in hb_oracle

    combined_dataflow_graph: networkx.DiGraph[ProcessState | InodeVersionNode] = networkx.DiGraph()
    quad_to_state = {}
    edges: list[tuple[ptypes.OpQuad | ProcessState, ptypes.OpQuad | ProcessState]] = []
    for pid, process in sorted(probe_log.processes.items()):
        last_state: ProcessState | None = None
        for exec_no, exec in sorted(process.execs.items()):
            for deduplicator, (inputs, outputs, quads) in enumerate(get_read_write_batches(
                    hbg,
                    hb_oracle,
                    dataflow_graph,
                    pid,
                    exec,
            )):
                state = ProcessState(pid, exec_no, deduplicator)
                for input in inputs:
                    if isinstance(input, InodeVersionNode):
                        combined_dataflow_graph.add_edge(input, state)
                    else:
                        edges.append((input, state))
                for output in outputs:
                    if isinstance(output, InodeVersionNode):
                        combined_dataflow_graph.add_edge(state, output)
                    else:
                        edges.append((state, output))
                for quad in quads:
                    quad_to_state[quad] = state
                if last_state is not None:
                    combined_dataflow_graph.add_edge(last_state, state)
                last_state = state
    for src, dst in edges:
        src_state = quad_to_state[src] if isinstance(src, ptypes.OpQuad) else src
        dst_state = quad_to_state[dst] if isinstance(dst, ptypes.OpQuad) else dst
        combined_dataflow_graph.add_edge(src_state, dst_state)
    return combined_dataflow_graph


def _get_first_and_last_quad(
        hbg: ptypes.HbGraph,
        pid: ptypes.Pid,
        exec_no: ptypes.ExecNo,
) -> tuple[ptypes.OpQuad, ptypes.OpQuad]:
    # we can guess the first_quad
    first_quad = ptypes.OpQuad(pid, exec_no, pid.main_thread(), 0)
    assert all([
        quad.pid != pid or quad.exec_no != exec_no
        for quad in hbg.predecessors(first_quad)
    ])
    dfs = graph_utils.search_with_pruning(hbg, first_quad, False)
    last_op_no = first_quad.op_no
    for quad in dfs:
        assert quad
        if quad.pid == pid and quad.exec_no == exec_no and quad.tid == pid.main_thread():
            last_op_no = max(last_op_no, quad.op_no)
            dfs.send(True)
        else:
            dfs.send(False)
    last_quad = ptypes.OpQuad(pid, exec_no, pid.main_thread(), last_op_no)
    assert all([
        quad.pid != pid or quad.exec_no != exec_no
        for quad in hbg.successors(last_quad)
    ]), (quad, list(hbg.successors(last_quad)))
    return first_quad, last_quad


def get_read_write_batches_simple(
        hbg: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
        pid: ptypes.Pid,
        exec: ptypes.Exec,
) -> It[tuple[
    It[ptypes.OpQuad | InodeVersionNode],
    It[ptypes.OpQuad | InodeVersionNode],
    It[ptypes.OpQuad],
]]:
    first_quad, last_quad = _get_first_and_last_quad(hbg, pid, exec.exec_no)
    quads = graph_utils.topological_sort_depth_first(
        hbg,
        first_quad,
        reachability_oracle=hb_oracle,
    )
    for quad in quads:
        assert quad
        if quad.pid == pid and quad.exec_no == exec.exec_no:
            dataflow_inputs = [
                input
                for input in dataflow_graph.predecessors(quad)
                if isinstance(input, InodeVersionNode) or input.pid != quad.pid
            ]
            dataflow_outputs = [
                output
                for output in dataflow_graph.successors(quad)
                if isinstance(output, InodeVersionNode) or output.pid != quad.pid
            ]
            yield frozenset(dataflow_inputs), frozenset(dataflow_outputs), frozenset({quad})
            assert quads.send(True) is None
        elif hb_oracle.is_reachable(quad, last_quad):
            assert quads.send(True) is None
        else:
            assert quads.send(False) is None


class _State(enum.Enum):
    READ = enum.auto()
    READ_WRITE = enum.auto()
    WRITE = enum.auto()
    def next(self) -> _State:
        return {
            _State.READ: _State.READ_WRITE,
            _State.READ_WRITE: _State.WRITE,
            _State.WRITE: _State.READ,
        }[self]


def get_read_write_batches(
        hbg: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
        pid: ptypes.Pid,
        exec: ptypes.Exec,
) -> It[tuple[
    It[ptypes.OpQuad | InodeVersionNode],
    It[ptypes.OpQuad | InodeVersionNode],
    It[ptypes.OpQuad],
]]:
    """Get read and write epochs.

    E.g., all the reads done by the process up until a write, then all the writes done by the process.

    """
    first_quad, last_quad = _get_first_and_last_quad(hbg, pid, exec.exec_no)
    assert first_quad in hb_oracle
    assert last_quad in hb_oracle
    assert hb_oracle.is_reachable(first_quad, last_quad)
    queue: dict[int, set[ptypes.OpQuad]] = collections.defaultdict(set, [(0, {first_quad})])
    queue_inverse = {first_quad: 0}
    state = _State.READ
    inputs = []
    outputs = []
    incorporated_quads = set()
    last_queue_0 = frozenset[ptypes.OpQuad]()
    last_last_queue_0 = frozenset[ptypes.OpQuad]()
    last_last_last_queue_0 = frozenset[ptypes.OpQuad]()

    #print(f"Coalescing {pid} {exec.exec_no}")

    def remove(quad: ptypes.OpQuad) -> None:
        #print("      Removed")
        degree = queue_inverse[quad]
        del queue_inverse[quad]
        queue[degree].remove(quad)

    def enqueue_successors(quad: ptypes.OpQuad) -> bool:
        #print("      Enqueue Successors:")
        mini_progress = False
        for successor in hbg.successors(quad):
            if successor in queue_inverse:
                in_degree = queue_inverse[successor]
                queue[in_degree].remove(successor)
                in_degree -= 1
            else:
                in_degree = sum(
                    hb_oracle.is_reachable(first_quad, predecessor_of_successor)
                    for predecessor_of_successor in hbg.predecessors(successor)
                    if predecessor_of_successor != quad
                )
                assert successor in hb_oracle
            #print(f"      {successor} {in_degree=}")
            assert in_degree >= 0
            queue_inverse[successor] = in_degree
            queue[in_degree].add(successor)
            mini_progress = in_degree == 0 or mini_progress
        return mini_progress

    while queue[0]:
        #print(f"  state={state.name}")

        # Detect if we are stuck in an infinite loop
        if queue[0] == last_last_last_queue_0:
            raise RuntimeError("No progress made")
        last_last_last_queue_0 = last_last_queue_0
        last_last_queue_0 = last_queue_0
        last_queue_0 = frozenset(queue[0])

        # We have to progress in order to keep looping
        progress = True
        while progress:
            progress = False
            for quad in list(queue[0]):
                #print(f"    {quad=}")
                # FIXME: This should include previous exec / next exec
                # Often, files will get passed from one to another.
                # But when I included the ExecOp, it broke this algorithm.
                # because ExecOp is an node with inputs and outputs, which is neither admissible during read-state nor write-state.
                # So I patched it in the caller to creat the exec edges
                # Also fix this in the "simple version"
                dataflow_inputs = ([
                    input
                    for input in dataflow_graph.predecessors(quad)
                    if isinstance(input, InodeVersionNode) or input.pid != quad.pid
                ] if quad in dataflow_graph else [])
                dataflow_outputs = ([
                    output
                    for output in dataflow_graph.successors(quad)
                    if isinstance(output, InodeVersionNode) or output.pid != quad.pid
                ] if quad in dataflow_graph else [])

                if (not hb_oracle.is_reachable(quad, last_quad)) and quad != last_quad and quad != first_quad:
                    #print("      Not ancestor of last_quad")
                    remove(quad)
                elif quad.pid != pid or quad.exec_no != exec.exec_no:
                    #print("      Other process, but ancestor of last_quad")
                    remove(quad)
                    progress = enqueue_successors(quad) or progress
                elif quad not in dataflow_graph.nodes():
                    #print("      No dataflow connections")
                    # No dataflow connections, but it could still be pointed to.
                    incorporated_quads.add(quad)
                    remove(quad)
                    progress = enqueue_successors(quad) or progress
                elif (
                        (state == _State.READ and not dataflow_outputs) or
                        (state == _State.READ_WRITE and dataflow_inputs and dataflow_outputs) or
                        (state == _State.WRITE and not dataflow_inputs)
                ):
                    #print("      Matches state")
                    incorporated_quads.add(quad)
                    remove(quad)
                    progress = enqueue_successors(quad) or progress
                    inputs.extend(dataflow_inputs)
                    outputs.extend(dataflow_outputs)

                    # Bit of a special case, since we can only take one node in READ_WRITE mode.
                    if state == _State.READ_WRITE:
                        break
                else:
                    #print("      Doesn't match state")
                    pass
            # No more progress can be made
            # because READ_WRITE only takes one node.
            # Otherwise, we keep trying to make progress
            if state == _State.READ_WRITE:
                break

        if state == _State.WRITE:
            yield tuple(inputs), tuple(outputs), frozenset(incorporated_quads)
            #print("  Yielding bundle:")
            #print("    input")
            # for input in inputs:
            #     print(f"     {input}")
            #print("    output")
            # for output in outputs:
            #     print(f"      {output}")
            #print("    incorporated_quads")
            # for quad in incorporated_quads:
            #     print(f"      {quad}")
            inputs.clear()
            outputs.clear()
            incorporated_quads.clear()

        state = state.next()

    if incorporated_quads:
        yield tuple(inputs), tuple(outputs), frozenset(incorporated_quads)
        #print("  Yielding bundle:")
        #print("    input")
        # for input in inputs:
        #     print(f"      {input}")
        #print("    output")
        # for output in outputs:
        #     print(f"      {output}")
        #print("    incorporated_quads")
        # for quad in sorted(incorporated_quads, key=lambda node: node.op_no):
        #     print(f"      {quad}")
    else:
        assert not inputs
        assert not outputs

    if any(queue.values()):
        queue = {
            in_degree: in_degree_queue
            for in_degree, in_degree_queue in queue.items()
            if in_degree_queue
        }
        # FIXME: re-enable warning
        #warnings.warn(ptypes.UnusualProbeLog(f"No progress made, but queue not complete: {queue}"))


def validate_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: DataflowGraph,
        # dataflow_graph_tc: DataflowGraph | None,
) -> None:
    if not networkx.is_directed_acyclic_graph(dataflow_graph):
        cycle = list(networkx.find_cycle(dataflow_graph))
        warnings.warn(ptypes.UnusualProbeLog(f"Found a cycle in graph: {cycle}"))

    if not networkx.is_weakly_connected(dataflow_graph):
        warnings.warn(ptypes.UnusualProbeLog(
            "Graph is not weakly connected:"
            f" {'\n'.join(map(str, networkx.weakly_connected_components(dataflow_graph)))}"
        ))

    inode_to_last_node: dict[ptypes.Inode, None | InodeVersionNode] = {
        inode: None
        for node in dataflow_graph.nodes()
        if isinstance(node, set)
        for inode in node
    }
    for node in networkx.topological_sort(dataflow_graph):
        if isinstance(node, set):
            for inode_version in node:
                inode = inode_version.inode
                version = inode_version.version
                if last_node := inode_to_last_node.get(inode):
                    if version in {last_node.version, last_node.version + 1}:
                        warnings.warn(ptypes.UnusualProbeLog(f"We went from {last_node.version} to {version}"))
                else:
                    if version not in {0, 1}:
                        warnings.warn(ptypes.UnusualProbeLog(
                            f"Version of an initial access should be 0 or 1 not {version}"
                        ))
                inode_to_last_node[inode] = inode_version

def filter_paths(
        dfg: CompressedDataflowGraph,
        inode_to_paths: Map[ptypes.Inode, It[pathlib.Path]],
        ignore_paths: It[pathlib.Path | re.Pattern[str]],
) -> CompressedDataflowGraph:
    def node_mapper(node: networkx.DiGraph[ptypes.OpQuad] | tuple[InodeVersionNode, ...]) -> networkx.DiGraph[ptypes.OpQuad] | tuple[InodeVersionNode, ...]:
        if isinstance(node, networkx.DiGraph):
            return node
        elif isinstance(node, tuple):
            output_ivls = []
            for ivl in node:
                for ignore_path in ignore_paths:
                    for inode_path in inode_to_paths.get(ivl.inode, ()):
                        if isinstance(ignore_path, pathlib.Path):
                            if inode_path.is_relative_to(ignore_path):
                                print(f"ignoring {inode_path} (matches {ignore_path})")
                                # this indoe_path matches ignore
                                break
                        elif isinstance(ignore_path, re.Pattern):
                            if ignore_path.match(str(inode_path)):
                                print(f"ignoring {inode_path} (matches {ignore_path})")
                                # this indoe_path matches ignore
                                break
                        else:
                            raise TypeError(
                                value=ignore_path,
                                type=type(ignore_path),
                                expected=pathlib.Path | re.Pattern[str]
                            )
                    else:
                        # not broken, no inode_path matched this ignore_path
                        # Continue checking other inode_paths
                        continue
                    # not continued, some indoe_path matched this ignore_path
                    # Stop looking for other inode_paths
                    break
                else:
                    # not broken, no inode_path matched any ignore_paths
                    output_ivls.append(ivl)
                # Whether or not this ivl was appended, continue checking other ivls
            return tuple(output_ivls)
        else:
            raise TypeError(
                node,
                type(node),
                "networkx.DiGraph[ptypes.OpQuad] | tuple[InodeVersionNode, ...]",
            )

    return graph_utils.map_nodes(
        # Get rid of the nodes where we removed EVERY inode.
        node_mapper,
        graph_utils.filter_nodes(
            lambda node: isinstance(node, networkx.DiGraph) or bool(node_mapper(node)),
            dfg,
        ),
    )


def shorten_path(
        input: pathlib.Path,
        max_path_length: int,
        max_path_segment_length: int,
        relative_to: pathlib.Path | None,
) -> str:
    print(input, relative_to)
    if input.is_absolute() and relative_to and input.is_relative_to(relative_to):
        input = input.relative_to(relative_to)
    output = ("/" if input.is_absolute() else "") + "/".join(
        textwrap.shorten(segment, width=max_path_segment_length)
        for segment in input.parts
        if segment != "/"
    )
    if len(output) > max_path_length:
        output = "..." + output[-max_path_length:]
    return output


def label_inode_set(
        inodes: Seq[InodeVersionNode],
        data: NodeData,
        inode_to_path: Map[ptypes.Inode, It[pathlib.Path]],
        relative_to: pathlib.Path | None,
        max_path_length: int,
        max_path_segment_length: int,
        max_paths_per_inode: int,
        max_inodes_per_set: int,
) -> None:
    inode_labels = []
    for inode_version in inodes[:max_inodes_per_set]:
        inode_label = []
        paths = inode_to_path.get(inode_version.inode, frozenset[pathlib.Path]())
        for path in sorted(set(paths), key=lambda path: len(str(path)))[:max_paths_per_inode]:
            inode_label.append(shorten_path(path, max_path_length, max_path_segment_length, relative_to))
        inode_labels.append("\n".join(inode_label).strip() + f" v{inode_version.version}")
    if len(inodes) > max_inodes_per_set:
        inode_labels.append("...other inodes")
    data["label"] = "\n".join(inode_labels)
    data["shape"] = "rectangle"
    data["id"] = str(hash(inodes))


def stringify_init_exec(
        op: ops.InitExecEpochOp,
        max_args: int = 5,
        max_arg_length: int = 80,
) -> str:
    args = " ".join(
        textwrap.shorten(
            arg.decode(errors="backslashreplace"),
            width=max_arg_length,
        )
        for arg in op.argv[:max_args]
    )
    if len(op.argv) > max_args:
        args += "..."
    return f"exec {args}"

def label_quads_graph(
        quads_graph: networkx.DiGraph[ptypes.OpQuad],
        data: NodeData,
        probe_log: ptypes.ProbeLog,
        max_args: int,
        max_arg_length: int,
) -> None:
    data["shape"] = "oval"
    data["id"] = id(quads_graph)
    data["label"] = ""
    for quad in quads_graph.nodes():
        data["cluster"] = f"Process {quad.pid}"
        op_data = probe_log.get_op(quad).data
        if isinstance(op_data, ops.InitExecEpochOp):
            if quad.pid == probe_log.get_root_pid() and quad.exec_no == 0:
                data["label"] += "(root)\n"
            data["label"] += stringify_init_exec(op_data) + "\n"
        else:
            data["label"] += f"\n{op_data.__class__.__name__}"
    data["label"] = data["label"].strip()


def label_nodes(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: CompressedDataflowGraph,
        inode_to_path: Map[ptypes.Inode, It[pathlib.Path]],
        relative_to: pathlib.Path,
        max_args: int = 5,
        max_arg_length: int = 80,
        max_path_length: int = 40,
        max_path_segment_length: int = 20,
        max_paths_per_inode: int = 1,
        max_inodes_per_set: int = 1,
) -> None:
    for node, data in dataflow_graph.nodes(data=True):
        match node:
            case networkx.DiGraph():
                label_quads_graph(node, data, probe_log, max_args=max_args, max_arg_length=max_arg_length)
            case tuple():
                label_inode_set(
                    node,
                    data,
                    inode_to_path,
                    relative_to,
                    max_path_length=max_path_length,
                    max_path_segment_length=max_path_segment_length,
                    max_paths_per_inode=max_paths_per_inode,
                    max_inodes_per_set=max_inodes_per_set,
                )
