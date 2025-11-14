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


@dataclasses.dataclass(frozen=True, order=True)
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
Col: typing.TypeAlias = collections.abc.Collection
T_co = typing.TypeVar("T_co", covariant=True)
V_co = typing.TypeVar("V_co", covariant=True)
FrozenDict: typing.TypeAlias = frozendict.frozendict[T_co, V_co]
NodeData: typing.TypeAlias = dict[str, typing.Any]

@dataclasses.dataclass(frozen=True)
class Quads:
    inner: frozenset[ptypes.OpQuad]
    exec_pair: ptypes.ExecPair

    def __str__(self) -> str:
        ret = f"{self.exec_pair} "
        thread_to_quads: Map[ptypes.Tid, It[ptypes.OpQuad]] = util.groupby_dict(self.inner, lambda quad: quad.tid)
        for tid, quads in thread_to_quads.items():
            ret += f"TID {tid} "
            min_op_no = min(quad.op_no for quad in quads)
            max_op_no = max(quad.op_no for quad in quads)
            if min_op_no == max_op_no:
                ret += f"op {min_op_no} "
            else:
                ret += f"ops {min_op_no}-{max_op_no} "
        return ret[:-1]

    def __repr__(self) -> str:
        return str(self)

    def __iter__(self) -> typing.Iterator[ptypes.OpQuad]:
        return iter(self.inner)

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
    Map[ptypes.Inode, It[pathlib.Path]],
    ptypes.HbGraph,
    graph_utils.ReachabilityOracle[ptypes.OpQuad],
]:
    # Find the HBG
    hbg = hb_graph.probe_log_to_hb_graph(probe_log)

    # Remove unnecessary nodes
    hbg = hb_graph.retain_only(probe_log, hbg, _is_interesting_for_dataflow)

    # Find the ops in each thread, which is lesser than the total ops after we do retain
    thread_to_ops_unsorted: Map[ptypes.ThreadTriple, It[ptypes.OpQuad]] = util.groupby_dict(
        hbg.nodes(),
        key_func=lambda quad: quad.thread_triple(), 
    )
    thread_to_ops = {
        thread_triple: sorted(thread_quads, key=lambda quad: quad.op_no)
        for thread_triple, thread_quads in thread_to_ops_unsorted.items()
    }
    exec_to_thread: Map[ptypes.ExecPair, It[ptypes.ThreadTriple]] = util.groupby_dict(
        thread_to_ops.keys(),
        key_func=lambda triple: triple.exec_pair(),
    )

    # DFG starts out with HBG
    # All HBG edges (program order, fork, join, exec) are also dataflow edges
    # But there are some dataflow edges/nodes that are not HB edges/nodes (e.g., inodes and edges-to/from-inodes).
    # We will add those next.
    dfg = typing.cast(
        UncompressedDataflowGraph,
        hbg.copy(),
    )

    # We will need an HB oracle on this to evaluate transitive reachability
    hb_oracle = graph_utils.PrecomputedReachabilityOracle[ptypes.OpQuad].create(hbg, progress=True)

    # For each inode, find the interval in which it was accessed
    inode_intervals, inode_to_paths = find_intervals(probe_log, hbg, hb_oracle, thread_to_ops)

    # For each inode
    for inode, interval_infos in tqdm.tqdm(inode_intervals.items(), desc="Add intervals for inode to graph"):
        add_inode_intervals(inode, interval_infos, dfg, hb_oracle)
        # TODO: Check these with the recorded mtime

    # Add DFG edges for threads
    add_thread_dataflow_edges(hbg, hb_oracle, dfg, exec_to_thread, thread_to_ops)

    # TODO: We should return a map from path to inodes and inode to IVNs
    # These maps facilitate "does A depend on B?" queries.

    # Make dfg have the same datatype as a compressed graph
    return null_compression(dfg), inode_to_paths, hbg, hb_oracle


def null_compression(
        dfg: UncompressedDataflowGraph,
) -> DataflowGraph:
    def node_mapper(node: ptypes.OpQuad | InodeVersionNode) -> Quads | IVNs:
        if isinstance(node, ptypes.OpQuad):
            return Quads(frozenset({node}), node.exec_pair())
        elif isinstance(node, InodeVersionNode):
            return IVNs({node})
        else:
            raise TypeError(node)
    return graph_utils.map_nodes(node_mapper, dfg, check=False)


@charmonium.time_block.decor()
def visualize_dataflow_graph(
        dfg: DataflowGraph,
        inode_to_paths: Map[ptypes.Inode, It[pathlib.Path]],
        ignore_paths: It[pathlib.Path | re.Pattern[str]],
        relative_to: pathlib.Path,
        probe_log: ptypes.ProbeLog,
        compress: bool,
) -> DataflowGraph:
    dfg2 = filter_paths(dfg, inode_to_paths, ignore_paths)
    if compress:
        dfg3 = compress_graph(probe_log, dfg2)
    else:
        dfg3 = dfg2
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
        print(ptypes.UnusualProbeLog(f"Unknown path for {inode} at quad {quad}"))
        return None


@charmonium.time_block.decor(print_start=True)
def find_intervals(
        probe_log: ptypes.ProbeLog,
        hb_graph: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        thread_to_ops: typing.Mapping[ptypes.ThreadTriple, Seq[ptypes.OpQuad]],
) -> tuple[Map[ptypes.Inode, It[IntervalInfo]], Map[ptypes.Inode, It[pathlib.Path]]]:
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
                    inode_to_paths[inode] = {pathlib.Path(f"pipe:{inode.number % 2**16:4x}")}
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
        verbose: bool = False,
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
    if verbose:
        print(f"  Searching for {fds_to_watch} {inode_version.inode}")
    start = datetime.datetime.now()

    for i, quad in enumerate(quads):
        assert quad is not None
        assert hb_oracle.is_reachable(initial_quad, quad)
        op_data = probe_log.get_op(quad).data
        if verbose:
            print(f"    {quad} {op_data.__class__.__name__}, {fds_to_watch}")
        match op_data:
            case ops.OpenOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    if verbose:
                        print(f"    Subsequent open of a different {op_data.fd} pruned")
                    assert quads.send(False) is None
                    continue
            case ops.ExecOp():
                for fd in list(fds_to_watch[quad.pid]):
                    if cloexecs[quad.pid][fd]:
                        if verbose:
                            print(f"    Cloexec {fd}")
                        fds_to_watch[quad.pid].remove(fd)
                        if not fds_to_watch[quad.pid]:
                            closes[quad.pid].add(quad)
            case ops.CloseOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    if verbose:
                        print(f"    Close {op_data.fd}")
                    fds_to_watch[quad.pid].remove(op_data.fd)
                    if not fds_to_watch[quad.pid]:
                        closes[quad.pid].add(quad)
                else:
                    if verbose:
                        print(f"    Close {op_data.fd} (unrelated)")
            case ops.DupOp():
                if op_data.old in fds_to_watch[quad.pid]:
                    fds_to_watch[quad.pid].add(op_data.new)
                    cloexecs[quad.pid][op_data.new] = bool(op_data.flags & os.O_CLOEXEC)
                    if verbose:
                        print(f"    Dup {op_data.old} -> {op_data.new} {fds_to_watch}")
            case ops.CloneOp():
                if op_data.task_type == ptypes.TaskType.TASK_PID:
                    target = ptypes.Pid(op_data.task_id)
                    if fds_to_watch[quad.pid]:
                        opens[target].add(ptypes.OpQuad(target, ptypes.initial_exec_no, target.main_thread(), 0))
                    if verbose:
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
            if verbose:
                print("  Last quad in this process; autoclosing")
            closes[quad.pid].add(quad)
            fds_to_watch[quad.pid].clear()

        if not fds_to_watch[quad.pid]:
            if verbose:
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
    ret = graph_utils.Interval.union(hb_oracle, *(
        hb_oracle.interval(frozenset(opens[pid]), frozenset(closes[pid]))
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
    dfg: UncompressedDataflowGraph,
    exec_to_threads: Map[ptypes.ExecPair, It[ptypes.ThreadTriple]],
    thread_to_ops: Map[ptypes.ThreadTriple, It[ptypes.OpQuad]],
) -> None:
    # For all threads, every op in this thread can dataflow to every op in each sibling thread that does not happen before it.
    # We only need to add an edge to the first op in each sibling thread that does not happen before it.
    # We only need to do this for ops just before the ops in this thread that happen-after an op in the other thread.

    topo_sort = networkx.topological_sort(hb_graph)
    topo_ordering = {
        node: idx
        for idx, node in enumerate(topo_sort)
    }
    for threads in tqdm.tqdm(
            exec_to_threads.values(),
            desc="exec pairs (implicit comm)",
    ):
        connect_implicit_communication(
            # FIXME: Take advantage of the fact that we know two ops in the same thread can never be peers.
            itertools.chain.from_iterable(thread_to_ops[thread] for thread in threads),
            topo_ordering,
            dfg,
            hb_graph,
            hb_oracle,
        )


def connect_implicit_communication(
        quads: It[ptypes.OpQuad],
        topo_ordering: Map[ptypes.OpQuad, int],
        dfg: UncompressedDataflowGraph,
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
            # FIXME speed this up
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
            dfg.add_edge(src, peer, style="dotted")


def add_inode_intervals(
        inode: ptypes.Inode,
        intervals: It[IntervalInfo],
        dfg: UncompressedDataflowGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
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
            if s0.interval.all_greater_than(hb_oracle, s1.interval)
        ]
    )

    # Use the transitive closure to eliminate unnecessary edges (makes versions more precise)
    # Suppose A, B, and C are read/writes where A before B, B before C, and A before C, what version does C see?
    # A and B happen before C, but it would only see B, because B happens "more closely before"; i.e., A -> B -> C.
    # This is equivalent to the transitive reduction.
    interval_hb = networkx.transitive_reduction(interval_hb)

    # Construct the hb oracle, which will help us know the peer and reachable nodes
    time_start = datetime.datetime.now()
    interval_hb_oracle = graph_utils.PrecomputedReachabilityOracle[IntervalInfo].create(interval_hb)
    time_stop = datetime.datetime.now()
    if (time_stop - time_start).total_seconds() > 0.1:
        print(f"TC on {len(interval_hb)} intervals took a long time")

    prior_versions = dict[IntervalInfo, int]()
    unused_version = itertools.count(1)
    for interval in tqdm.tqdm(intervals, desc="intervals"):
        if interval.access_mode.is_write:
            write_interval = interval

            prior_versions[write_interval] = next(unused_version)
            ivn = InodeVersionNode(inode, prior_versions[write_interval])
            dfg.add_node(
                ivn
            )
            for node in write_interval.bottom():
                # Non-transient version output
                dfg.add_edge(node, ivn)

            if not write_interval.access_mode.is_mutating_write:
                # Mutating write, e.g., "replace the 100th byte with 23".
                # The _process_ can't be influened by the current contents of the ivn,
                # But the outputted version _is_ influenced by the current version of the ivn.
                # Do same logic as read, but hook up to ivn instead of to process.
                # See `if interval.access_mode.is_read` section for details.

                # Transient version input
                concurrent_writes = get_concurrent_writes(write_interval, interval_hb, interval_hb_oracle)
                for pred_write_interval in concurrent_writes:
                    pred_ivn = InodeVersionNode(inode, next(unused_version))
                    dfg.add_node(pred_ivn)
                    for node in write_interval.bottom():
                        dfg.add_edge(pred_ivn, ivn)

                # Non-transient version input
                preceeding_writes = get_latest_preceeding_writes(write_interval, interval_hb, interval_hb_oracle)
                for pred_write_interval in preceeding_writes:
                    pred_ivn = InodeVersionNode(
                        inode,
                        prior_versions[pred_write_interval],
                    )
                    dfg.add_edge(pred_ivn, ivn)

                # If no preceeding writes, we pick up whatever version existed prior to execution
                if not preceeding_writes:
                    pred_ivn = InodeVersionNode(
                        inode,
                        0,
                    )
                    dfg.add_node(pred_ivn)
                    dfg.add_edge(pred_ivn, ivn)

        # FIXME: If interval I and J are simultaneous read-write intervals on inode N,
        # I and J implicitly communicate through N.
        # Even when I == J.
        # Need to call connect_implicit_communication(I, J).

        # FIXME: there is nothing in a pipe before execution and nothing left in the pipe after execution

        if interval.access_mode.is_read:
            read_interval = interval

            # If a read and a write are concurrent,
            # the read can access the version produced while the write is in progress.
            # That version _might_ not be accessed by any other reader.
            # It's a version unique to the reader-writer pair, aka "transient version".
            concurrent_writes = get_concurrent_writes(read_interval, interval_hb, interval_hb_oracle)
            for write_interval in concurrent_writes:
                ivn = InodeVersionNode(inode, next(unused_version))
                dfg.add_node(ivn)
                for node in write_interval.bottom():
                    dfg.add_edge(node, ivn)
                for node in read_interval.top():
                    dfg.add_edge(ivn, node)

            # Hook up the existing, non-transient version of each immediately preceeding write interval
            # "Immediately prceeding" but ignoring reads,
            # E.g., "write -> read -> read"; the write's version is used for both reads.
            preceeding_writes = get_latest_preceeding_writes(read_interval, interval_hb, interval_hb_oracle)
            for pred_write_interval in preceeding_writes:
                ivn = InodeVersionNode(inode, prior_versions[pred_write_interval])
                for node in read_interval.top():
                    dfg.add_edge(ivn, node)

            # If no preceeding writes, we pick up whatever version existed prior to execution
            if not preceeding_writes:
                ivn = InodeVersionNode(inode, 0)
                dfg.add_node(ivn)
                for node in read_interval.top():
                    dfg.add_edge(ivn, node)


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
        dfg: DataflowGraph,
) -> None:
    if not networkx.is_weakly_connected(dfg):
        warnings.warn(ptypes.UnusualProbeLog(
            "Graph is not weakly connected:"
            f" {'\n'.join(map(str, networkx.weakly_connected_components(dfg)))}"
        ))

    for node in dfg.nodes():
        if isinstance(node, Quads):
            assert len(set(quad.exec_pair() for quad in node)) == 1, node


def filter_paths(
        dfg: DataflowGraph,
        inode_to_paths: Map[ptypes.Inode, It[pathlib.Path]],
        ignore_paths: It[pathlib.Path | re.Pattern[str]],
) -> DataflowGraph:
    def node_mapper(node: Quads | IVNs) -> Quads | IVNs:
        if isinstance(node, Quads):
            return node
        elif isinstance(node, IVNs):
            output_ivns = []
            for ivn in sorted(node):
                for inode_path in sorted(inode_to_paths.get(ivn.inode, ())):
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
    dfg_collapsed_loops = dfg_in
    #dfg_collapsed_loops = collapse_loops(dfg_in)
    print(f"Collapsing loops {len(dfg_in.nodes())} -> {len(dfg_collapsed_loops.nodes())} nodes; {len(dfg_in.edges())} -> {len(dfg_collapsed_loops.edges())} edges")
    print(f"{sum(len(scc) > 1 for scc in networkx.strongly_connected_components(dfg_in))} non-trivial SCCs -> {sum(len(scc) > 1 for scc in networkx.strongly_connected_components(dfg_collapsed_loops))}")

    # Remove unnecessary nodes
    # This is an in-place operation
    dfg_chains_reduced = dfg_collapsed_loops.copy()
    remove_chains(dfg_chains_reduced)
    print(f"Removed unnecessary process nodes {len(dfg_collapsed_loops.nodes())} -> {len(dfg_chains_reduced.nodes())} nodes; {len(dfg_collapsed_loops.edges())} -> {len(dfg_chains_reduced.edges())}")
    print(f"{sum(isinstance(node, Quads) for node in dfg_collapsed_loops.nodes())} quad nodes -> {sum(isinstance(node, Quads) for node in dfg_chains_reduced.nodes())}")

    # Group twin inodes
    dfg_twin_inodes_combined = graph_utils.map_nodes(
        compressed_dfg_node_flattener,
        graph_utils.combine_twin_nodes(dfg_chains_reduced, lambda node: isinstance(node, IVNs)),
    )
    print(f"Combined twin inodes {len(dfg_chains_reduced.nodes())} -> {len(dfg_twin_inodes_combined.nodes())} nodes; {len(dfg_chains_reduced.edges())} -> {len(dfg_twin_inodes_combined.edges())}")
    print(f"{sum(isinstance(node, IVNs) for node in dfg_chains_reduced.nodes())} inode nodes -> {sum(isinstance(node, IVNs) for node in dfg_twin_inodes_combined.nodes())}")

    return dfg_twin_inodes_combined


def compressed_dfg_node_flattener(nodes: It[Quads | IVNs]) -> Quads | IVNs:
    if all(isinstance(node, Quads) for node in nodes):
        quadss = typing.cast(It[Quads], nodes)
        exec_pairs = frozenset(quad.exec_pair() for quads in quadss for quad in quads)
        assert len(exec_pairs) == 1, exec_pairs
        exec_pair = next(iter(exec_pairs))
        return Quads(frozenset({quad for quads in quadss for quad in quads}), exec_pair)
    elif all(isinstance(node, IVNs) for node in nodes):
        ivnss = typing.cast(It[IVNs], nodes)
        return IVNs(ivn for ivns in ivnss for ivn in ivns)
    else:
        raise TypeError(nodes)


def collapse_loops(dfg: DataflowGraph) -> DataflowGraph:
    # Assert all quad groups are from the same exec pair
    assert all(not isinstance(node, Quads) or len(set(quad.exec_pair() for quad in node)) == 1 for node in dfg.nodes())
    ivns = []
    quad_partitions = []
    for component in networkx.strongly_connected_components(dfg):
        quad_to_node: typing.Mapping[ptypes.OpQuad, Quads] = {
            quad: node
            for node in component
            if isinstance(node, Quads)
            for quad in node
        }
        # if len(component) > 1:
        #     print(len(component), len(quad_to_node))
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
                # if len(same_exec_nodes) > 1:
                #     print("Collapsing", same_exec_nodes)
                quad_partitions.append(same_exec_nodes)

            # Don't forget to add inodes in a singleton set
            for node in component:
                if isinstance(node, IVNs):
                    ivns.append(node)
        else:
            # Add back these components
            for node in component:
                if isinstance(node, Quads):
                    quad_partitions.append(frozenset({node}))
                else:
                    ivns.append(node)

    # Assert we haven't left out any nodes
    # This transformation doesn't change the number of nodes.
    # See the next one for that.
    assert set().union(*quad_partitions) | set(ivns) == set(dfg.nodes())

    # Ordering the partitions to make the order of nodes in the quotient_graph deterministic.

    quotient: "networkx.DiGraph[frozenset[IVNs | Quads]]" \
        = networkx.quotient_graph(dfg, quad_partitions + [{ivn} for ivn in ivns])

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
    assert all(not isinstance(node, Quads) or util.all_unique(quad.exec_pair() for quad in node) for node in quotient_flattened.nodes())

    return quotient_flattened


def split_neighbors(
        dfg: DataflowGraph, node: Quads
) -> tuple[Seq[Quads], Seq[Quads], Seq[Quads | IVNs], Seq[Quads | IVNs]]:
    predecessors: Map[bool, Seq[Quads | IVNs]] = util.groupby_dict(
        dfg.predecessors(node),
        key_func=lambda other: isinstance(other, Quads) and node.exec_pair == node.exec_pair,
    )
    successors: Map[bool, Seq[Quads | IVNs]] = util.groupby_dict(
        dfg.successors(node),
        key_func=lambda other: isinstance(other, Quads) and node.exec_pair == node.exec_pair,
    )
    return (
        typing.cast(Seq[Quads], predecessors.get(True, ())),
        typing.cast(Seq[Quads], successors.get(True, ())),
        predecessors.get(False, ()),
        successors.get(False, ()),
    )


def is_chain_member(dfg: DataflowGraph, node: Quads) -> bool:
    "Return if node is a member of chain that can be removed."
    preds_inside, succs_inside, _, _ = split_neighbors(dfg, node)
    return len(preds_inside) <= 1 and len(succs_inside) <= 1


def remove_chains(dfg: DataflowGraph) -> None:
    checked = set[Quads]()
    for node in list(dfg.nodes()):
        if isinstance(node, Quads) and node not in checked and is_chain_member(dfg, node) and (chain := get_chain(dfg, node)) and len(chain) > 1:

            # Don't need to recheck any nodes on this chain
            assert all(node not in checked for node in chain[1:-1])
            checked.update(chain)

            subchains = get_subchains(dfg, chain)

            assert networkx.is_weakly_connected(dfg)
            for subchain in subchains:
                # Only bother if we can substitute one node in place of a subchain longer than one node.
                if len(subchain) > 1:
                    remove_subchain(dfg, subchain)


def remove_subchain(
        dfg: DataflowGraph,
        subchain_nodes: Seq[Quads],
) -> None:
    new_node = Quads(
        frozenset({quad for node in subchain_nodes for quad in node}),
        subchain_nodes[0].exec_pair,
    )
    # Preserve the property that all quads only coalesce quads of the same exec_pair
    assert all([
        quad.exec_pair() == new_node.exec_pair
        for node in subchain_nodes
        for quad in node
    ])
    subchain_set = frozenset(subchain_nodes)
    subchain_succs = [
        succ
        for node in subchain_nodes
        for succ in dfg.successors(node)
        if succ not in subchain_set
    ]
    subchain_preds = [
        pred
        for node in subchain_nodes
        for pred in dfg.predecessors(node)
        if pred not in subchain_set
    ]
    for pred in subchain_preds:
        dfg.add_edge(pred, new_node, color="green")
    for succ in subchain_succs:
        dfg.add_edge(new_node, succ, color="green")
    for node in subchain_nodes:
        dfg.nodes(data=True)[node]["color"] = "blue"
    dfg.nodes(data=True)[new_node]["color"] = "green"
    for i, node in enumerate(subchain_nodes):
        # print("Removing", i, node, hash(node))
        # ensure we don't try to access this node again
        # assert node in checked
        dfg.remove_node(node)
    assert networkx.is_weakly_connected(dfg)


def get_chain(dfg: DataflowGraph, node: Quads) -> Seq[Quads]:
    chain = collections.deque([node])
    preds, succs, _, _ = split_neighbors(dfg, node)

    # Find the start
    while preds:
        if preds[0].exec_pair != node.exec_pair:
            break
        chain.appendleft(preds[0])
        if is_chain_member(dfg, preds[0]):
            preds, _, _, _ = split_neighbors(dfg, preds[0])
        else:
            break

    # Find the end
    while succs:
        if succs[0].exec_pair != node.exec_pair:
            break
        chain.append(succs[0])
        if is_chain_member(dfg, succs[0]):
            _, succs, _, _ = split_neighbors(dfg, succs[0])
        else:
            break

    chain2 = tuple(chain)
    assert networkx.is_path(dfg, chain2)
    assert all(is_chain_member(dfg, node) for node in chain2[1:-1])
    assert all(node.exec_pair == chain2[0].exec_pair for node in chain2)
    assert util.all_unique(chain2)
    return chain2


def get_subchains(
        dfg: DataflowGraph,
        chain: Seq[Quads],
) -> It[Seq[Quads]]:
    # Split chain into subchains based on read/write.
    # A subchain can have read-nodes or write-nodes.
    # But once it accepts one write-node, it can never take another read-node.
    # Collapsing [R1, W2, R3] would create a false dataflow path R3 -> W2
    # But collapsing [R1, R2, W3, W4] creates no false dataflow paths,
    # as the paths {R1, R2} -> {W3, W4} are genuine.
    subchains: list[tuple[
        list[Quads],        # 0: nodes in subchain
        util.Box[bool],        # 1: read mode (else write mode)
    ]] = [([], util.Box(True))]

    for node in chain:
        succs_within, preds_within, preds_other, succs_other = split_neighbors(dfg, node)
        if preds_other and succs_other:
            if subchains[-1][1].get():
                # RW in read-mode
                # Append to chain
                # Switch to write mode
                subchains[-1][0].append(node)
                subchains[-1][1].set(False)
            else:
                # RW in write-mode
                # Make a new subchain, in write-mode
                subchains.append(([node], util.Box(False)))
        elif preds_other:
            if subchains[-1][1].get():
                # R in read-mode
                # Append to subchain
                subchains[-1][0].append(node)
            else:
                # R in write-mode
                # New subchain chain, in read-mode
                subchains.append(([node], util.Box(True)))
        elif succs_other:
            if subchains[-1][1].get():
                # write in read-mode
                # Append to subchain
                # Switch to write-mode
                subchains[-1][0].append(node)
                subchains[-1][1].set(False)
            else:
                # write in write-mode
                # Append to subchain
                subchains[-1][0].append(node)
        else:
            # No ins or outs. Whatever the mode, append
            subchains[-1][0].append(node)

    # All chain nodes end up in a subchain
    all_subchain_nodes = [node for subchain, _ in subchains for node in subchain]
    assert all_subchain_nodes == list(chain)

    # Subchains should not contain nodes already deleted
    assert all(node in dfg.nodes() for node in all_subchain_nodes)

    return [quad[0] for quad in subchains]


def shorten_path(
        input: pathlib.Path,
        max_path_length: int,
        max_path_segment_length: int,
        relative_to: pathlib.Path | None,
) -> str:
    if relative_to and (input.is_absolute() and relative_to.is_absolute()):
        input2 = input.relative_to(relative_to, walk_up=True)
        if sum(part == ".." for part in input2.parts) > 3:
            input2 = input
    else:
        input2 = input
    output = ("/" if input2.is_absolute() else "") + "/".join(
        textwrap.shorten(segment, width=max_path_segment_length)
        for segment in input2.parts
        if segment != "/"
    )
    if len(output) > max_path_length:
        output = "..." + output[-max_path_length:]
    return output


def label_inode_set(
        inodes: IVNs,
        inodes_label_bank: Map[str | None, typing.Iterator[int]],
        data: NodeData,
        inode_to_path: Map[ptypes.Inode, It[pathlib.Path]],
        relative_to: pathlib.Path | None,
        max_path_length: int,
        max_path_segment_length: int,
        max_paths_per_inode: int,
        max_inodes_per_set: int,
) -> None:
    inode_labels = []
    # Sorting ensures consistent labels
    inodes_list = sorted(inodes)
    for inode_version in inodes_list[:max_inodes_per_set]:
        inode_label = []
        paths = inode_to_path.get(inode_version.inode, frozenset[pathlib.Path]())
        for path in sorted(set(paths), key=lambda path: len(str(path)))[:max_paths_per_inode]:
            inode_label.append(shorten_path(path, max_path_length, max_path_segment_length, relative_to))
        inode_labels.append("\n".join(inode_label).strip() + f" v{inode_version.version}")
    if len(inodes) > max_inodes_per_set:
        inode_labels.append("...other inodes")
    data["label"] = "\n".join(inode_labels)
    data["shape"] = "rectangle"
    data["inodes"] = ",".join(str(inode.inode.number) for inode in inodes)
    first_inode = next(iter(inodes)) if inodes else None
    first_inode_paths = inode_to_path.get(first_inode.inode) if first_inode else None
    first_inode_path = next(iter(first_inode_paths)) if first_inode_paths else None
    first_inode_path_name = first_inode_path.name if first_inode_path else None
    id = next(inodes_label_bank[first_inode_path_name])
    data["id"] = f"{first_inode_path_name}_v{id}"


def stringify_init_exec(
        op_data: ops.InitExecEpochOp,
        max_args: int,
        max_arg_length: int,
        max_path_segment_length: int,
        relative_to: pathlib.Path | None,
) -> str:
    args = [arg.decode(errors="backslashreplace") for arg in op_data.argv[0:max_args]]
    ret = ""
    ret += shorten_path(pathlib.Path(args[0]), max_arg_length, max_path_segment_length, relative_to)
    ret += "\n"
    ret += "\n".join(
        shorten_path(pathlib.Path(arg), max_arg_length, max_path_segment_length, None)
        if "/" in arg else
        textwrap.shorten(arg, width=max_arg_length)
        for arg in args[1:]
    )
    if len(op_data.argv) > max_args:
        ret += "\n..."
    return ret


def label_quads_graph(
        quads: Quads,
        exe_label_bank: Map[str, typing.Iterator[int]],
        exec_pair_label_bank: dict[ptypes.ExecPair, tuple[str, int, typing.Iterator[int]]],
        data: NodeData,
        probe_log: ptypes.ProbeLog,
        max_args: int,
        max_arg_length: int,
        max_path_segment_length: int,
        relative_to: pathlib.Path | None,
) -> None:
    data["shape"] = "oval"
    exec_pair = quads.exec_pair

    if exec_pair not in exec_pair_label_bank:
        # TODO: should probable have a way to go from exec_pair -> InitExecEpochOp in ptypes.ProbeLog
        # We do this in several places throughout the code.
        first_op_data = probe_log.get_op(ptypes.OpQuad(exec_pair.pid, exec_pair.exec_no, exec_pair.pid.main_thread(), 0)).data
        assert isinstance(first_op_data, ops.InitExecEpochOp)
        exe = first_op_data.argv[0].decode()
        exe_id = next(exe_label_bank[exe])
        exec_pair_label_bank[exec_pair] = (exe, exe_id, itertools.count())

    exe, exe_id, quad_counter = exec_pair_label_bank[exec_pair]
    data["id"] = f"{exe}_exec{exe_id}_op{next(quad_counter)}"
    data["label"] = ""
    for quad in quads:
        data["cluster"] = f"Process {quad.pid}"
        op_data = probe_log.get_op(quad).data
        if isinstance(op_data, ops.InitExecEpochOp):
            if quad.exec_no == 0:
                if quad.pid == probe_log.get_root_pid():
                    data["label"] += "Root process:\n"
                else:
                    data["label"] += "(child process)"
                    break
            data["label"] += stringify_init_exec(op_data, max_args=max_args, max_arg_length=max_arg_length, max_path_segment_length=max_path_segment_length, relative_to=relative_to) + "\n"
    data["label"] = data["label"].strip()
    data["exec_pair"] = f"pid={exec_pair.pid} exec={exec_pair.exec_no}"
    tid_to_quads: Map[ptypes.Tid, It[ptypes.OpQuad]] = util.groupby_dict(quads, key_func=lambda quad: quad.tid)
    data["quads"] = "; ".join(
        f"tid={tid} ops=" + ",".join(str(quad.op_no) for quad in tid_quads)
        for tid, tid_quads in tid_to_quads.items()
    )


def node_sort_key(node: Quads | IVNs | ptypes.OpQuad | InodeVersionNode) -> typing.Any:
    """Node sorting gives us deterministic labels. Works on compressed or uncompressed graphs."""
    if isinstance(node, ptypes.OpQuad):
        return (1, node)
    elif isinstance(node, InodeVersionNode):
        return (0, node)
    elif isinstance(node, Quads):
        min_quad = min(node)
        return (1, min_quad)
    elif isinstance(node, IVNs):
        min_ivn = min(node)
        return (0, min_ivn)
    else:
        raise TypeError(node)


@charmonium.time_block.decor(print_start=False)
def label_nodes(
        probe_log: ptypes.ProbeLog,
        dfg: DataflowGraph,
        inode_to_path: Map[ptypes.Inode, It[pathlib.Path]],
        relative_to: pathlib.Path | None,
        max_args: int = 5,
        max_arg_length: int = 80,
        max_path_length: int = 40,
        max_path_segment_length: int = 20,
        max_paths_per_inode: int = 2,
        max_inodes_per_set: int = 10,
) -> None:
    inode_label_bank = collections.defaultdict[str | None, typing.Iterator[int]](lambda: itertools.count())
    exe_label_bank = collections.defaultdict[str, typing.Iterator[int]](lambda: itertools.count())
    exec_pair_label_bank = dict[ptypes.ExecPair, tuple[str, int, typing.Iterator[int]]]()
    for node in tqdm.tqdm(sorted(dfg.nodes(), key=node_sort_key), desc="label dfg"):
        data2 = dfg.nodes(data=True)[node]
        match node:
            case Quads():
                label_quads_graph(
                    node,
                    exe_label_bank,
                    exec_pair_label_bank,
                    data2,
                    probe_log,
                    max_args=max_args,
                    max_arg_length=max_arg_length,
                    max_path_segment_length=max_path_segment_length,
                    relative_to=relative_to,
                )
            case IVNs():
                label_inode_set(
                    node,
                    inode_label_bank,
                    data2,
                    inode_to_path,
                    relative_to,
                    max_path_length=max_path_length,
                    max_path_segment_length=max_path_segment_length,
                    max_paths_per_inode=max_paths_per_inode,
                    max_inodes_per_set=max_inodes_per_set,
                )
