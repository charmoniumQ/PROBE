from __future__ import annotations
import collections
import dataclasses
import datetime
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
class Quads(frozenset[ptypes.OpQuad]):
    ...
class IVNs(frozenset[InodeVersionNode]):
    ...

if typing.TYPE_CHECKING:
    UncompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuad | InodeVersionNode]
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[Quads | IVNs]
else:
    UncompressedDataflowGraph = networkx.DiGraph
    DataflowGraph = networkx.DiGraph


@charmonium.time_block.decor(print_start=False)
def hb_graph_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
) -> tuple[
    DataflowGraph,
    Map[ptypes.Inode, frozenset[pathlib.Path]],
    ptypes.HbGraph,
    graph_utils.ReachabilityOracle[ptypes.OpQuad],
]:
    # Find the HBG
    hbg = hb_graph.probe_log_to_hb_graph(probe_log)

    # Remove unnecessary nodes
    hbg = hb_graph.retain_only(probe_log, hbg, _is_interesting_for_dataflow)

    # Find the ops in each thread, which is lesser than the total ops after we do retain
    thread_to_ops_unsorted = collections.defaultdict(set)
    for quad in hbg.nodes():
        thread_to_ops_unsorted[quad.thread_triple()].add(quad)
    thread_to_ops = {
        thread_triple: sorted(thread_quads, key=lambda quad: quad.op_no)
        for thread_triple, thread_quads in thread_to_ops_unsorted.items()
    }
    del thread_to_ops_unsorted # only use sorted from now on.

    # DFG starts out with HBG
    # All HBG edges (program order, fork, join, exec) are also dataflow edges
    # But there are some dataflow edges/nodes that are not HB edges/nodes (e.g., inodes and edges-to/from-inodes).
    # We will add those next.
    dataflow_graph = typing.cast(
        UncompressedDataflowGraph,
        hbg.copy(),
    )

    # We will need an HB oracle on this to evaluate transitive reachability
    hb_oracle = graph_utils.PrecomputedReachabilityOracle[ptypes.OpQuad].create(hbg)

    # For each inode, find the interval in which it was accessed
    inode_intervals, inode_to_paths = find_intervals(probe_log, hbg, hb_oracle, thread_to_ops)

    # For each inode
    for inode, interval_infos in tqdm.tqdm(inode_intervals.items(), desc="Add intervals for inode to graph"):
        add_inode_intervals(inode, interval_infos, dataflow_graph)
        # TODO: Check these with the recorded mtime

    # Add DFG edges for threads
    add_thread_dataflow_edges(hbg, hb_oracle, dataflow_graph)

    # TODO: We should return a map from path to inodes and inode to IVNs
    # These maps facilitate "does A depend on B?" queries.

    # Make dfg have the same datatype as a compressed graph

    return null_compression(dataflow_graph), inode_to_paths, hbg, hb_oracle


def null_compression(
        dfg: UncompressedDataflowGraph,
) -> DataflowGraph:
    def node_mapper(node: ptypes.OpQuad | InodeVersionNode) -> Quads | IVNs:
        if isinstance(node, ptypes.OpQuad):
            return Quads({node})
        elif isinstance(node, InodeVersionNode):
            return IVNs({node})
        else:
            raise TypeError(node)
    return graph_utils.map_nodes(node_mapper, dfg, check=False)


@charmonium.time_block.decor(print_start=False)
def visualize_dataflow_graph(
        dfg: DataflowGraph,
        inode_to_paths: Map[ptypes.Inode, frozenset[pathlib.Path]],
        ignore_paths: Seq[pathlib.Path | re.Pattern[str]],
        relative_to: pathlib.Path,
        probe_log: ptypes.ProbeLog,
) -> DataflowGraph:
    dfg2 = filter_paths(dfg, inode_to_paths, ignore_paths)
    dfg3 = compress_graph(probe_log, dfg2)
    label_nodes(
        probe_log,
        dfg3,
        inode_to_paths,
        relative_to=relative_to,
    )
    return dfg3


@dataclasses.dataclass(frozen=True)
class IntervalInfo:
    access_mode: ptypes.AccessMode
    inode_version: ptypes.InodeVersion
    interval: graph_utils.Interval[ptypes.OpQuad]

    # TODO: Make this graph general
    # We currently assume the ndoes are structured into processes.
    # But this algorithm should work however the nodes are structured.
    # Especially since two processes may implicitly share information with network or mmap.

    def top(self) -> It[ptypes.OpQuad]:
        yield from self.interval.upper_bound

    def bottom(self) -> It[ptypes.OpQuad]:
        yield from self.interval.lower_bound


def _is_interesting_for_dataflow(node: ptypes.OpQuad, op: ops.Op) -> bool:
    return isinstance(
        op.data,
        (ops.OpenOp, ops.CloseOp, ops.CloneOp, ops.DupOp, ops.ExecOp, ops.ChdirOp, ops.InitExecEpochOp, ops.WaitOp, ops.MkFileOp, ops.ExitThreadOp),
    ) and getattr(op.data, "ferrno", 0) == 0


def _score_children(parent: ptypes.OpQuad, child: ptypes.OpQuad) -> int:
    return 0 if parent.tid == child.tid else 1 if parent.pid == child.pid else 2 if parent.pid <= child.pid else 3


def _to_path(
        cwds: Map[ptypes.Pid, pathlib.Path],
        inode_to_paths: Map[ptypes.Inode, set[pathlib.Path]],
        quad: ptypes.OpQuad,
        path: ops.Path,
) -> pathlib.Path | None:
    inode = ptypes.InodeVersion.from_probe_path(path).inode
    if path.path:
        path_arg = pathlib.Path(path.path.decode())
        if quad.pid in cwds:
            return cwds[quad.pid] / path_arg
        elif path_arg.is_absolute():
            return path_arg
        else:
            warnings.warn(ptypes.UnusualProbeLog(f"Unknown cwd at quad {quad}; Did we not see InitExecEpoch?"))
            return None
    elif inode in inode_to_paths:
        return list(inode_to_paths[inode])[-1]
    else:
        #print(ptypes.UnusualProbeLog(f"Unknown path for {inode} at quad {quad}")) # FIXME
        return None


def find_intervals(
        probe_log: ptypes.ProbeLog,
        hb_graph: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        thread_to_ops: typing.Mapping[ptypes.ThreadTriple, Seq[ptypes.OpQuad]],
) -> tuple[Map[ptypes.Inode, Seq[IntervalInfo]], Map[ptypes.Inode, frozenset[pathlib.Path]]]:
    inode_to_intervals = collections.defaultdict[ptypes.Inode, list[IntervalInfo]](list)
    cwds = dict[ptypes.Pid, pathlib.Path]()
    inode_to_paths = collections.defaultdict[ptypes.Inode, set[pathlib.Path]](set)

    quads = graph_utils.topological_sort_depth_first(hb_graph, score_children=_score_children)
    for quad in tqdm.tqdm(quads, total=len(hb_graph), desc="Ops -> intervals"):
        assert quad is not None
        op_data = probe_log.get_op(quad).data
        match op_data:
            case ops.InitExecEpochOp():
                cwd_path = _to_path(cwds, inode_to_paths, quad, op_data.cwd)
                if cwd_path:
                    cwds[quad.pid] = cwd_path
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.exe)
                interval = graph_utils.Interval.singleton(hb_oracle, quad)
                inode_to_intervals[inode_version.inode].append(IntervalInfo(ptypes.AccessMode.EXEC, inode_version, interval))
                exe_path = _to_path(cwds, inode_to_paths, quad, op_data.exe)
                if exe_path:
                    inode_to_paths[inode_version.inode].add(exe_path)
            case ops.ChdirOp():
                path = _to_path(cwds, inode_to_paths, quad, op_data.path)
                if path:
                    cwds[quad.pid] = path
            case ops.MkFileOp():
                if op_data.file_type == ptypes.FileType.PIPE.value:
                    inode = ptypes.InodeVersion.from_probe_path(op_data.path).inode
                    inode_to_paths[inode] = {pathlib.Path("/[pipe]")}
            case ops.OpenOp():
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.path)
                interval = find_closes(
                    probe_log,
                    hb_graph,
                    hb_oracle,
                    thread_to_ops,
                    quad,
                    op_data.fd,
                    bool(op_data.flags & os.O_CLOEXEC),
                    inode_version,
                )
                access = ptypes.AccessMode.from_open_flags(op_data.flags)
                inode_to_intervals[inode_version.inode].append(IntervalInfo(access, inode_version, interval))
                path = _to_path(cwds, inode_to_paths, quad, op_data.path)
                if path:
                    inode_to_paths[inode_version.inode].add(path)
        assert quads.send(True) is None
    return inode_to_intervals, {inode: frozenset(paths) for inode, paths in inode_to_paths.items()}


def find_closes(
        probe_log: ptypes.ProbeLog,
        hb_graph: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        thread_to_ops: typing.Mapping[ptypes.ThreadTriple, Seq[ptypes.OpQuad]],
        initial_quad: ptypes.OpQuad,
        initial_fd: int,
        initial_cloexec: bool,
        inode_version: ptypes.InodeVersion,
) -> graph_utils.Interval[ptypes.OpQuad]:
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
        for pid, fds in fds_to_watch.items():
            if fds:
                last_exec_no = max(
                    triple.exec_no
                    for triple in thread_to_ops.keys()
                    if triple.pid == pid
                )
                last_quad = thread_to_ops[ptypes.ThreadTriple(pid, last_exec_no, pid.main_thread())][-1]
                assert hb_oracle.is_reachable(initial_quad, last_quad), (initial_quad, pid, fds, last_quad)
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
    ret = graph_utils.Interval.union(*(
        graph_utils.Interval(hb_oracle, frozenset(opens[pid]), frozenset(closes[pid]))
        for pid in opens.keys()
    ))
    end = datetime.datetime.now()
    duration = end - start
    if duration > datetime.timedelta(seconds=0.1):
        print(f"find_closes: Build {n_proc} interval union in {duration.total_seconds():.1f}")
    return ret


def add_thread_dataflow_edges(
    hb_graph: ptypes.HbGraph,
    hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
    dataflow_graph: UncompressedDataflowGraph,
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
        dataflow_graph: UncompressedDataflowGraph,
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
            # This is N^2 with the number of quads in an implicitly communicating cabal
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


def add_inode_intervals(
        inode: ptypes.Inode,
        intervals: It[IntervalInfo],
        dataflow_graph: UncompressedDataflowGraph,
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
    interval_hb: networkx.DiGraph[IntervalInfo] = graph_utils.create_digraph(
        intervals,
        [
            (s0, s1)
            for s0, s1 in itertools.permutations(intervals, 2)
            if s0.interval.all_greater_than(s1.interval)
        ]
    )

    # Use the transitive closure to eliminate unnecessary edges (makes versions more precise)
    # Suppose A, B, and C are read/writes where A before B, B before C, and A before C, what version does C see?
    # A and B happen before C, but it would only see B, because B happens "more closely before"; i.e., A -> B -> C.
    # This is equivalent to the transitive reduction.
    interval_hb = networkx.transitive_reduction(interval_hb)

    # Construct the hb oracle, which will help us know the peer and reachable nodes
    interval_hb_oracle = graph_utils.PrecomputedReachabilityOracle[IntervalInfo].create(interval_hb)

    for interval in intervals:
        if interval.access_mode.is_write:
            write_interval = interval

            # TODO: properly version IVNs
            ivn = InodeVersionNode(inode, hash(write_interval) ^ hash(inode))
            dataflow_graph.add_node(
                ivn
            )
            for node in write_interval.top():
                dataflow_graph.add_edge(node, ivn)
                if not write_interval.access_mode.is_mutating_write:
                    # Mutating write, e.g., "replace the 100th byte with 23".
                    # The _process_ can't be influened by the current contents of the ivn,
                    # But the outputted version _is_ influenced by the current version of the ivn.
                    # Do same logic as read, but hook up to ivn instead of to process.
                    # See `if interval.access_mode.is_read` section for details.

                    # Transient versions
                    concurrent_writes = get_concurrent_writes(write_interval, interval_hb, interval_hb_oracle)
                    for pred_write_interval in concurrent_writes:
                        pred_ivn = InodeVersionNode(inode, hash(write_interval) ^ hash(pred_write_interval) ^ hash(inode))
                        dataflow_graph.add_node(pred_ivn)
                        for node in write_interval.bottom():
                            dataflow_graph.add_edge(pred_ivn, ivn)
                    # Non-transient versions
                    preceeding_writes = get_latest_preceeding_writes(write_interval, interval_hb, interval_hb_oracle)
                    for pred_write_interval in preceeding_writes:
                        pred_ivn = InodeVersionNode(inode, hash(pred_write_interval) ^ hash(inode))
                        dataflow_graph.add_edge(pred_ivn, ivn)

                    # If no preceeding writes, we pick up whatever version existed prior to execution
                    if not preceeding_writes:
                        pred_ivn = InodeVersionNode(inode, hash(write_interval) ^ hash(inode) ^ hash("pre-existing"))
                        dataflow_graph.add_node(pred_ivn)
                        dataflow_graph.add_edge(pred_ivn, ivn)

        # FIXME: If interval I and J are simultaneous read-write intervals on inode N,
        # I and J implicitly communicate through N.
        # Even when I == J.
        # Need to call connect_implicit_communication(I, J).

        if interval.access_mode.is_read:
            read_interval = interval

            # If a read and a write are concurrent,
            # the read can access the version produced while the write is in progress.
            # That version _might_ not be accessed by any other reader.
            # It's a version unique to the reader-writer pair, aka "transient version".
            concurrent_writes = get_concurrent_writes(read_interval, interval_hb, interval_hb_oracle)
            for write_interval in concurrent_writes:
                ivn = InodeVersionNode(inode, hash(read_interval) ^ hash(write_interval) ^ hash(inode))
                dataflow_graph.add_node(ivn)
                for node in write_interval.bottom():
                    dataflow_graph.add_edge(node, ivn)
                for node in read_interval.top():
                    dataflow_graph.add_edge(ivn, node)

            # Hook up the existing, non-transient version of each immediately preceeding write interval
            # "Immediately prceeding" but ignoring reads,
            # E.g., "write -> read -> read"; the write's version is used for both reads.
            preceeding_writes = get_latest_preceeding_writes(read_interval, interval_hb, interval_hb_oracle)
            for write_interval in preceeding_writes:
                ivn = InodeVersionNode(inode, hash(read_interval) ^ hash(inode))
                for node in read_interval.top():
                    dataflow_graph.add_edge(ivn, node)

            # If no preceeding writes, we pick up whatever version existed prior to execution
            if not preceeding_writes:
                ivn = InodeVersionNode(inode, hash(read_interval) ^ hash(inode) ^ hash("pre-existing"))
                dataflow_graph.add_node(ivn)
                for node in read_interval.top():
                    dataflow_graph.add_edge(ivn, node)


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


def validate_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: DataflowGraph,
) -> None:
    if not networkx.is_weakly_connected(dataflow_graph):
        warnings.warn(ptypes.UnusualProbeLog(
            "Graph is not weakly connected:"
            f" {'\n'.join(map(str, networkx.weakly_connected_components(dataflow_graph)))}"
        ))

    for node in dataflow_graph.nodes():
        if isinstance(node, Quads):
            assert len(set(quad.exec_pair() for quad in node)) == 1, node


def filter_paths(
        dfg: DataflowGraph,
        inode_to_paths: Map[ptypes.Inode, frozenset[pathlib.Path]],
        ignore_paths: It[pathlib.Path | re.Pattern[str]],
) -> DataflowGraph:
    def node_mapper(node: Quads | IVNs) -> Quads | IVNs:
        if isinstance(node, Quads):
            return node
        elif isinstance(node, IVNs):
            output_ivns = []
            for ivn in node:
                for inode_path in inode_to_paths.get(ivn.inode, ()):
                    for ignore_path in ignore_paths:
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
                            raise TypeError(ignore_path, pathlib.Path | re.Pattern[str])
                    else:
                        # not broken, no inode_path matched this ignore_path
                        # Continue checking other inode_paths
                        continue
                    # not continued, some indoe_path matched this ignore_path
                    # Stop looking for other inode_paths
                    break
                else:
                    # not broken, no inode_path matched any ignore_paths
                    output_ivns.append(ivn)
                # Whether or not this ivn was appended, continue checking other ivns
            return IVNs(output_ivns)
        else:
            raise TypeError(node, Quads | IVNs)

    def node_filter(node: Quads | IVNs) -> bool:
        return bool(node_mapper(node))

    return graph_utils.map_nodes(
        # Only keep the kept nodes within each set
        node_mapper,
        graph_utils.filter_nodes(
            # Get rid of the nodes where we removed EVERY inode.
            node_filter,
            dfg,
        ),
    )


def compress_graph(
        probe_log: ptypes.ProbeLog,
        dfg_in: DataflowGraph,
) -> DataflowGraph:
    # Collapse loops
    dfg_collapsed_loops = collapse_loops(dfg_in)
    print(f"Collapsing loops {len(dfg_in.nodes())} -> {len(dfg_collapsed_loops.nodes())} nodes; {len(dfg_in.edges())} -> {len(dfg_collapsed_loops.edges())} edges")
    print(f"{sum(len(scc) > 1 for scc in networkx.strongly_connected_components(dfg_in))} non-trivial SCCs -> {sum(len(scc) > 1 for scc in networkx.strongly_connected_components(dfg_collapsed_loops))}")

    # Remove unnecessary nodes
    dfg_nodes_removed = graph_utils.retain_nodes_in_digraph(
        dfg_collapsed_loops,
        frozenset({
            node
            for node in dfg_collapsed_loops.nodes()
            if not isinstance(node, Quads) or (
                    # at this point, we know we have an OpQuad
                    any(isinstance(probe_log.get_op(quad).data, ops.InitExecEpochOp) for quad in node)
                    or any([isinstance(predecessor, IVNs) for predecessor in dfg_collapsed_loops.predecessors(node)])
                    or any([isinstance(successor  , IVNs) for successor   in dfg_collapsed_loops.successors  (node)])
            )
        }),
    )
    print(f"Removed unnecessary process nodes {len(dfg_collapsed_loops.nodes())} -> {len(dfg_nodes_removed.nodes())} nodes; {len(dfg_collapsed_loops.edges())} -> {len(dfg_nodes_removed.edges())}")
    print(f"{sum(isinstance(node, Quads) for node in dfg_collapsed_loops.nodes())} quad nodes -> {sum(isinstance(node, Quads) for node in dfg_nodes_removed.nodes())}")

    # Group twin inodes
    dfg_twin_inodes_combined = graph_utils.map_nodes(
        compressed_dfg_node_flattener,
        graph_utils.combine_twin_nodes(dfg_nodes_removed, lambda node: isinstance(node, IVNs)),
    )
    print(f"Combined twin inodes {len(dfg_nodes_removed.nodes())} -> {len(dfg_twin_inodes_combined.nodes())} nodes; {len(dfg_nodes_removed.edges())} -> {len(dfg_twin_inodes_combined.edges())}")
    print(f"{sum(isinstance(node, IVNs) for node in dfg_nodes_removed.nodes())} inode nodes -> {sum(isinstance(node, IVNs) for node in dfg_twin_inodes_combined.nodes())}")

    return dfg_twin_inodes_combined


def compressed_dfg_node_flattener(nodes: frozenset[Quads | IVNs]) -> Quads | IVNs:
    return (
        Quads(quad for node in nodes if isinstance(node, Quads) for quad in node) if all(isinstance(node, Quads) for node in nodes) else
        IVNs(ivn for node in nodes if isinstance(node, IVNs) for ivn in node) if all(isinstance(node, IVNs) for node in nodes) else
        util.raise_(TypeError(nodes, It[Quads | IVNs]))
    )


def collapse_loops(dfg: DataflowGraph) -> DataflowGraph:
    # Assert all quad groups are from the same exec pair
    assert all(not isinstance(node, Quads) or len(set(quad.exec_pair() for quad in node)) == 1 for node in dfg.nodes())

    partitions: set[frozenset[Quads | IVNs]] = set()
    for component in networkx.strongly_connected_components(dfg):
        quad_to_node: typing.Mapping[ptypes.OpQuad, Quads] = {
            quad: node
            for node in component
            if isinstance(node, Quads)
            for quad in node
        }
        if len(component) > 1:
            print(len(component), len(quad_to_node))
        if len(quad_to_node) > 1:
            # We have a SCC with more than 1 op quad
            # Group together all nodes with the same exec_pair
            exec_pair_to_nodes: typing.Mapping[ptypes.ExecPair, It[ptypes.OpQuad]] = util.groupby_dict(
                quad_to_node.keys(),
                key_func=lambda quad: quad.exec_pair(),
            )
            for same_exec_quads in exec_pair_to_nodes.values():
                # For all quads in this SCC in the same exec pair,
                # Combine all nodes containing this quad.
                same_exec_nodes = frozenset(
                    quad_to_node[quad]
                    for quad in same_exec_quads
                )
                if len(same_exec_nodes) > 1:
                    print("Collapsing", same_exec_nodes)
                partitions.add(same_exec_nodes)

            # Don't forget to add inodes in a singleton set
            for node in component:
                if isinstance(node, IVNs):
                    partitions.add(frozenset({node}))
        else:
            # Add back these components
            for node in component:
                partitions.add(frozenset({node}))

    # Assert we haven't left out any nodes
    # This transformation doesn't change the number of nodes.
    # See the next one for that.
    assert frozenset().union(*partitions) == frozenset(dfg.nodes())

    quotient: "networkx.DiGraph[frozenset[IVNs | Quads]]" = networkx.quotient_graph(dfg, partitions)
    for _, data in quotient.nodes(data=True):
        del data["nnodes"]
        del data["density"]
        del data["graph"]
        del data["nedges"]
    for _, _, data in quotient.edges(data=True):
        del data["weight"]

    quotient_flattened = graph_utils.map_nodes(
        compressed_dfg_node_flattener,
        quotient,
    )

    # Assert all quad groups are from the same exec pair
    assert all(not isinstance(node, Quads) or len(set(quad.exec_pair() for quad in node)) == 1 for node in quotient_flattened.nodes())

    return quotient_flattened


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
        inodes: IVNs,
        data: NodeData,
        inode_to_path: Map[ptypes.Inode, frozenset[pathlib.Path]],
        relative_to: pathlib.Path | None,
        max_path_length: int,
        max_path_segment_length: int,
        max_paths_per_inode: int,
        max_inodes_per_set: int,
) -> None:
    inode_labels = []
    for inode_version in list(inodes)[:max_inodes_per_set]:
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
        quads: Quads,
        data: NodeData,
        probe_log: ptypes.ProbeLog,
        max_args: int,
        max_arg_length: int,
) -> None:
    data["shape"] = "oval"
    data["id"] = hash(quads)
    data["label"] = ""
    for quad in quads:
        data["cluster"] = f"Process {quad.pid}"
        op_data = probe_log.get_op(quad).data
        if isinstance(op_data, ops.InitExecEpochOp):
            if quad.pid == probe_log.get_root_pid() and quad.exec_no == 0:
                data["label"] += "(root)\n"
            data["label"] += stringify_init_exec(op_data) + "\n"
        else:
            data["label"] += f"\n{op_data.__class__.__name__}"
    data["label"] = data["label"].strip()


@charmonium.time_block.decor(print_start=False)
def label_nodes(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: DataflowGraph,
        inode_to_path: Map[ptypes.Inode, frozenset[pathlib.Path]],
        relative_to: pathlib.Path,
        max_args: int = 5,
        max_arg_length: int = 80,
        max_path_length: int = 40,
        max_path_segment_length: int = 20,
        max_paths_per_inode: int = 1,
        max_inodes_per_set: int = 1,
) -> None:
    for node, data in tqdm.tqdm(dataflow_graph.nodes(data=True), desc="label dfg"):
        data2 = typing.cast(dict[str, typing.Any], data)
        match node:
            case Quads():
                label_quads_graph(node, data2, probe_log, max_args=max_args, max_arg_length=max_arg_length)
            case IVNs():
                label_inode_set(
                    node,
                    data2,
                    inode_to_path,
                    relative_to,
                    max_path_length=max_path_length,
                    max_path_segment_length=max_path_segment_length,
                    max_paths_per_inode=max_paths_per_inode,
                    max_inodes_per_set=max_inodes_per_set,
                )
