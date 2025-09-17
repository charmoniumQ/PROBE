from __future__ import annotations
import collections
import dataclasses
import datetime
import enum
import fnmatch
import itertools
import os
import pathlib
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


It: typing.TypeAlias = collections.abc.Iterable
Map: typing.TypeAlias = collections.abc.Mapping
Seq: typing.TypeAlias = collections.abc.Sequence
FrozenDict: typing.TypeAlias = frozendict.frozendict

@dataclasses.dataclass(frozen=True)
class InodeVersionNode:
    """A particular version of the inode"""
    inode: ptypes.Inode
    version: int
    deduplicator: int | None = None

    def __str__(self) -> str:
        return f"{self.inode} version {self.version}"


@dataclasses.dataclass(frozen=True)
class ProcessState:
    pid: ptypes.Pid
    epoch_no: ptypes.ExecNo
    deduplicator: int


@dataclasses.dataclass(frozen=True)
class SegmentsPerProcess:
    segments: FrozenDict[ptypes.Pid, graph_utils.Segment[ptypes.OpQuad]]

    def all_greater_than(self, other: SegmentsPerProcess) -> bool:
        return all(
            pid in self.segments and self.segments[pid].all_greater_than(other_segment)
            for pid, other_segment in other.segments.items()
        )

    def __bool__(self) -> bool:
        "Whether any of the segments are non-empty"
        return any(self.segments.values())

    @staticmethod
    def singleton(
            hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
            quad: ptypes.OpQuad,
    ) -> SegmentsPerProcess:
        return SegmentsPerProcess(FrozenDict({quad.pid: graph_utils.Segment.singleton(hb_oracle, quad)}))

    @staticmethod
    def union(*segments_per_processs: SegmentsPerProcess) -> SegmentsPerProcess:
        union_segments_per_process = {}
        for segments_per_process in segments_per_processs:
            for process, segment in segments_per_process.segments.items():
                if process not in union_segments_per_process:
                    union_segments_per_process[process] = segment
                else:
                    union_segments_per_process[process] = graph_utils.Segment.union(
                        union_segments_per_process[process], segment,
                    )
        return SegmentsPerProcess(FrozenDict(union_segments_per_process))


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuad | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[ProcessState | frozenset[InodeVersionNode]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph


@dataclasses.dataclass(frozen=True)
class SegmentInfo:
    access_mode: ptypes.AccessMode
    inode_version: ptypes.InodeVersion
    segments: SegmentsPerProcess


def _retain_pred(node: ptypes.OpQuad, op: ops.Op) -> bool:
    return isinstance(
        op.data,
        (ops.OpenOp, ops.CloseOp, ops.CloneOp, ops.DupOp, ops.ExecOp, ops.ChdirOp, ops.InitExecEpochOp, ops.WaitOp, ops.MkFileOp),
    ) and getattr(op.data, "ferrno", 0) == 0


@charmonium.time_block.decor(print_start=False)
def hb_graph_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
) -> tuple[DataflowGraph, Map[ptypes.Inode, It[pathlib.Path]], graph_utils.ReachabilityOracle[ptypes.OpQuad]]:
    hbg = hb_graph.retain_only(probe_log, hbg, _retain_pred)
    hb_oracle = graph_utils.DualLabelReachabilityOracle[ptypes.OpQuad].create(hbg)
    inode_segments, inode_to_paths = find_segments(probe_log, hbg, hb_oracle)
    dataflow_graph = typing.cast(DataflowGraph, hbg.copy())
    for inode, segments in tqdm.tqdm(inode_segments.items(), desc="Add segments for inode to graph"):
        ordered_segments = order_segments(segments)
        version = 0
        start = datetime.datetime.now()
        for concurrent_segments in ordered_segments:
            version = add_inode_segments(hb_oracle, dataflow_graph, inode, concurrent_segments, version)
        end = datetime.datetime.now()
        duration = end - start
        if duration > datetime.timedelta(seconds=0.1):
            print(f"Adding segments took {duration.total_seconds()}")
    return dataflow_graph, inode_to_paths, hb_oracle


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
        warnings.warn(ptypes.UnusualProbeLog(f"Unkonwn path for {inode} at quad {quad}"))
        return pathlib.Path()


def find_segments(
        probe_log: ptypes.ProbeLog,
        hb_graph: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
) -> tuple[Map[ptypes.Inode, Seq[SegmentInfo]], Map[ptypes.Inode, Seq[pathlib.Path]]]:
    inode_to_segments = collections.defaultdict[ptypes.Inode, list[SegmentInfo]](list)
    cwds = dict[ptypes.Pid, pathlib.Path]()
    inode_to_paths = collections.defaultdict[ptypes.Inode, list[pathlib.Path]](list)

    quads = graph_utils.topological_sort_depth_first(hb_graph, score_children=_score_children)
    for quad in tqdm.tqdm(quads, total=len(hb_graph), desc="Ops -> segments"):
        assert quad is not None
        op_data = probe_log.get_op(quad).data
        match op_data:
            case ops.InitExecEpochOp():
                cwds[quad.pid] = _to_path(cwds, inode_to_paths, quad, op_data.cwd)
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.exe)
                segment = SegmentsPerProcess.singleton(hb_oracle, quad)
                inode_to_segments[inode_version.inode].append(SegmentInfo(ptypes.AccessMode.EXEC, inode_version, segment))
                inode_to_paths[inode_version.inode].append(_to_path(cwds, inode_to_paths, quad, op_data.exe))
            case ops.ChdirOp():
                cwds[quad.pid] = _to_path(cwds, inode_to_paths, quad, op_data.path)
            case ops.MkFileOp():
                if op_data.file_type == ptypes.FileType.PIPE.value:
                    inode = ptypes.InodeVersion.from_probe_path(op_data.path).inode
                    inode_to_paths[inode] = [pathlib.Path("/[pipe]")]
            case ops.OpenOp():
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.path)
                segment = find_closes(
                    probe_log,
                    hb_graph,
                    hb_oracle,
                    quad,
                    op_data.fd,
                    bool(op_data.flags & os.O_CLOEXEC),
                    inode_version,
                )
                access = ptypes.AccessMode.from_open_flags(op_data.flags)
                inode_to_segments[inode_version.inode].append(SegmentInfo(access, inode_version, segment))
                path = _to_path(cwds, inode_to_paths, quad, op_data.path)
                inode_to_paths[inode_version.inode].append(path)
        assert quads.send(True) is None
    return inode_to_segments, inode_to_paths


def find_closes(
        probe_log: ptypes.ProbeLog,
        hb_graph: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        initial_quad: ptypes.OpQuad,
        initial_fd: int,
        initial_cloexec: bool,
        inode_version: ptypes.InodeVersion,
) -> SegmentsPerProcess:
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
    #print(f"  Searching for {fds_to_watch} {inode_version.inode}")
    start = datetime.datetime.now()

    for i, quad in enumerate(quads):
        assert quad is not None
        assert hb_oracle.is_reachable(initial_quad, quad)
        op_data = probe_log.get_op(quad).data
        #print(f"    {quad} {op_data.__class__.__name__}, {fds_to_watch}")
        match op_data:
            case ops.OpenOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    #print(f"    Subsequent open of a different {op_data.fd} pruned")
                    assert quads.send(False) is None
                    continue
            case ops.ExecOp():
                for fd in list(fds_to_watch[quad.pid]):
                    if cloexecs[quad.pid][fd]:
                        #print(f"    Cloexec {fd}")
                        fds_to_watch[quad.pid].remove(fd)
                        if not fds_to_watch[quad.pid]:
                            closes[quad.pid].add(quad)
            case ops.CloseOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    if ptypes.InodeVersion.from_probe_path(op_data.path).inode == inode_version.inode:
                        #print(f"    Close {op_data.fd}")
                        fds_to_watch[quad.pid].remove(op_data.fd)
                        if not fds_to_watch[quad.pid]:
                            closes[quad.pid].add(quad)
                    else:
                        #print(f"    Subsequent close of a different {op_data.fd} pruned")
                        assert quads.send(False) is None
                        continue
                else:
                    pass
                    #print(f"    Close {op_data.fd} (unrelated)")
            case ops.DupOp():
                if op_data.old in fds_to_watch[quad.pid]:
                    if ptypes.InodeVersion.from_probe_path(op_data.path).inode == inode_version.inode:
                        fds_to_watch[quad.pid].add(op_data.new)
                        cloexecs[quad.pid][op_data.new] = bool(op_data.flags & os.O_CLOEXEC)
                        #print(f"    Dup {op_data.old} -> {op_data.new} {fds_to_watch}")
                    else:
                        #print(f"    Subsequent dup of a different {op_data.old} pruned")
                        assert quads.send(False) is None
                        continue
            case ops.CloneOp():
                if op_data.task_type == ptypes.TaskType.TASK_PID:
                    target = ptypes.Pid(op_data.task_id)
                    if fds_to_watch[quad.pid]:
                        opens[target].add(ptypes.OpQuad(target, ptypes.initial_exec_no, target.main_thread(), 0))
                    #print("    Clone")
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
            #print("  Last quad in this process; autoclosing")
            closes[quad.pid].add(quad)
            fds_to_watch[quad.pid].clear()

        if not fds_to_watch[quad.pid]:
            #print(f"  No more FDs to watch in {quad.pid}")
            assert quads.send(False) is None
        else:
            assert quads.send(True) is None

        fds_to_watch = collections.defaultdict(set, {
            pid: fds
            for pid, fds in fds_to_watch.items()
            if fds
        })

    if any(fds_to_watch.values()):
        # FIXME: re-enable this warning
        # warnings.warn(ptypes.UnusualProbeLog(
        #     f"We don't know where {fds_to_watch} got closed."
        # ))
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
    ret = SegmentsPerProcess(FrozenDict({
        pid: graph_utils.Segment(hb_oracle, frozenset(opens[pid]), frozenset(closes[pid]))
        for pid in opens.keys()
    }))
    end = datetime.datetime.now()
    duration = end - start
    if duration > datetime.timedelta(seconds=0.1):
        print(f"find_closes: Build {n_proc} segment union in {duration.total_seconds():.1f}")
    return ret


def order_segments(
        segments: It[SegmentInfo]
) -> It[It[SegmentInfo]]:
    segment_hb: networkx.DiGraph[SegmentInfo] = networkx.DiGraph()
    # FIXME: add_nodes_from
    assert all(isinstance(segment, SegmentInfo) for segment in segments), set(type(segment).__name__ for segment in segments)
    # segment_hb.add_nodes_from(list(segments))
    for segment in segments:
        hash(segment.access_mode)
        hash(segment.inode_version)
        hash(segment.segments)
        hash(segment.segments)
        hash(segment)
        segment_hb.add_node(segment)
    for s0, s1 in itertools.permutations(segments, 2):
        if s0.segments.all_greater_than(s1.segments):
            segment_hb.add_edge(s0, s1)
    return list(networkx.topological_generations(segment_hb))


def add_inode_segments(
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
        inode: ptypes.Inode,
        concurrent_segments: It[SegmentInfo],
        version: int,
) -> int:
    # TODO: This algorithm might create more cycles than necessary in some cases.
    # We consider a topological generation of segments at a time.
    # Everything in a future generaitno happens-after everything in the current generation.
    # But that doesn't mean everything in the current generation is concurrent/unordered. Maybe it does?
    # In either case, taking apart the SegmentsPerProcess into individual Segments of OpQuads may yield finer-grained dependencies.
    # A future algorithm might, get all the read-segments and write-segments for the whole time (not just one topo generation; so in obviating order_segments),
    # Let W := all segments (not segments_per_process) in which inode was written
    # Likewise, R := was read. Read-write?
    # Let G be the dag induced by the partial order of U union W based on the relation(a, b):
    # all of the last of a happen before any of the first of b.
    # While a and b are within one pid, they may be in different threads, and may have multiple firsts and lasts.
    # G2 := transitive reduction of G
    # The w->r edges of G2 become "major versions".
    # Reads will see the major version emenating from dominating, ancestral Ws (Ws that are not after another ancestral W).
    # But for each pair of write and read, we will introduce an "intermediate versions" if last of w do not all happen-before any of the first of r.
    # For every segment, either A is completely first, B is completely first, or idk. The former become edges, the middle anti-edges, and the latter, intermediate versions.
    # Even when neither happens before the other, still some sub-sequences may happen-before other sub-sequences.
    # That is a refinement for later.

    #print(f"  Concurrent segments for {inode} {version}")
    union_read_segments = SegmentsPerProcess.union(*[
        segment_info.segments
        for segment_info in concurrent_segments
        if segment_info.access_mode.is_read
    ])
    union_write_segments = SegmentsPerProcess.union(*[
        segment_info.segments
        for segment_info in concurrent_segments
        if segment_info.access_mode.is_write
    ])
    mutating_writes = SegmentsPerProcess.union(*[
        segment_info.segments
        for segment_info in concurrent_segments
        if segment_info.access_mode.is_write and segment_info.access_mode != ptypes.AccessMode.TRUNCATE_WRITE
    ])

    #print(f"    Readers: {sorted(union_read_segments.segments.keys())}")
    #print(f"    Writers: {sorted(union_write_segments.segments.keys())}")

    initial_version = version

    # Past writes -> current reads
    inode_version = InodeVersionNode(inode, version)
    for read_process, read_segment in union_read_segments.segments.items():
        for read_node in read_segment.upper_bound:
            dataflow_graph.add_edge(inode_version, read_node)

    # Current writes -> current reads
    if union_read_segments and union_write_segments:
        version += 1
        inode_version = InodeVersionNode(inode, version)
        initial_inode_version = InodeVersionNode(inode, initial_version)
        deduplicator = 0
        for write_process, write_segment in union_write_segments.segments.items():
            for read_process, read_segment in union_read_segments.segments.items():
                if write_process != read_process:
                    for write_node in write_segment.lower_bound:
                        for read_node in read_segment.upper_bound:
                            if not hb_oracle.is_reachable(read_node, write_node):
                                inode_version = InodeVersionNode(inode, version, deduplicator)
                                deduplicator += 1
                                dataflow_graph.add_edge(write_node, inode_version)
                                dataflow_graph.add_edge(inode_version, read_node)
            if write_segment in mutating_writes.segments.values():
                dataflow_graph.add_edge(initial_inode_version, inode_version)

    if union_write_segments:
        # If we did concurrent writes -> concurrent reads, we already handled this case
        # Current writes -> future reads
        version += 1
        inode_version = InodeVersionNode(inode, version)
        initial_inode_version = InodeVersionNode(inode, initial_version)
        for write_process, write_segment in union_write_segments.segments.items():
            for write_node in write_segment.lower_bound:
                dataflow_graph.add_edge(write_node, inode_version)
            if write_segment in mutating_writes.segments.values():
                dataflow_graph.add_edge(initial_inode_version, inode_version)

    return version

@charmonium.time_block.decor(print_start=False)
def combine_indistinguishable_inodes(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
    # FIXME: Make the elimination optional at a CLI level
    # Note the type still has to be converted from DataflowGraph to CompressedDataflowGraph
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
        dataflow_graph3 = graph_utils.combine_isomorphic_nodes(
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
    n_edges = len(dataflow_graph.edges())
    with charmonium.time_block.ctx("transitive reduction", print_start=False):
        dataflow_graph4 = graph_utils.transitive_reduction_cyclic_graph(dataflow_graph3)
    n_edges2 = len(dataflow_graph4.edges())
    print(f"Transitive reduction {n_edges} -> {n_edges2}")
    return typing.cast(CompressedDataflowGraph, dataflow_graph4)


def combine_adjacent_ops(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
) -> networkx.DiGraph[ProcessState | InodeVersionNode]:
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
    ])
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

    print(f"Coalescing {pid} {exec.exec_no}")

    def remove(quad: ptypes.OpQuad) -> None:
        print("      Removed")
        degree = queue_inverse[quad]
        del queue_inverse[quad]
        queue[degree].remove(quad)

    def enqueue_successors(quad: ptypes.OpQuad) -> bool:
        print("      Enqueue Successors:")
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
            #print(f"      {successor} {in_degree=}")
            assert in_degree >= 0
            queue_inverse[successor] = in_degree
            queue[in_degree].add(successor)
            mini_progress = in_degree == 0 or mini_progress
        return mini_progress

    while queue[0]:
        print(f"  state={state.name}")

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
                # print(f"    {quad=}")
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
                    print("      Not ancestor of last_quad")
                    remove(quad)
                elif quad.pid != pid or quad.exec_no != exec.exec_no:
                    print("      Other process, but ancestor of last_quad")
                    remove(quad)
                    progress = enqueue_successors(quad) or progress
                elif quad not in dataflow_graph.nodes():
                    print("      No dataflow connections")
                    # No dataflow connections, but it could still be pointed to.
                    incorporated_quads.add(quad)
                    remove(quad)
                    progress = enqueue_successors(quad) or progress
                elif (
                        (state == _State.READ and not dataflow_outputs) or
                        (state == _State.READ_WRITE and dataflow_inputs and dataflow_outputs) or
                        (state == _State.WRITE and not dataflow_inputs)
                ):
                    print("      Matches state")
                    incorporated_quads.add(quad)
                    remove(quad)
                    progress = enqueue_successors(quad) or progress
                    inputs.extend(dataflow_inputs)
                    outputs.extend(dataflow_outputs)

                    # Bit of a special case, since we can only take one node in READ_WRITE mode.
                    if state == _State.READ_WRITE:
                        break
                else:
                    print("      Doesn't match state")
                    pass
            # No more progress can be made
            # because READ_WRITE only takes one node.
            # Otherwise, we keep trying to make progress
            if state == _State.READ_WRITE:
                break

        if state == _State.WRITE:
            yield tuple(inputs), tuple(outputs), frozenset(incorporated_quads)
            print("  Yielding bundle:")
            print("    input")
            for input in inputs:
                print(f"     {input}")
            print("    output")
            for output in outputs:
                print(f"      {output}")
            print("    incorporated_quads")
            for quad in incorporated_quads:
                print(f"      {quad}")
            inputs.clear()
            outputs.clear()
            incorporated_quads.clear()

        state = state.next()

    if incorporated_quads:
        yield tuple(inputs), tuple(outputs), frozenset(incorporated_quads)
        print("  Yielding bundle:")
        print("    input")
        for input in inputs:
            print(f"      {input}")
        print("    output")
        for output in outputs:
            print(f"      {output}")
        print("    incorporated_quads")
        for quad in sorted(incorporated_quads, key=lambda node: node.op_no):
            print(f"      {quad}")
    else:
        assert not inputs
        assert not outputs

    if any(queue.values()):
        queue = {
            in_degree: in_degree_queue
            for in_degree, in_degree_queue in queue.items()
            if in_degree_queue
        }
        warnings.warn(ptypes.UnusualProbeLog(f"No progress made, but queue not complete: {queue}"))


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
        dfg: DataflowGraph,
        inode_to_paths: Map[ptypes.Inode, It[pathlib.Path]],
        ignore_paths: list[str],
) -> DataflowGraph:
    return typing.cast(
        DataflowGraph,
        dfg.subgraph([
            node
            for node in dfg.nodes()
            if not isinstance(node, InodeVersionNode) or not any(
                fnmatch.fnmatch(str(inode_path), ignore_path)
                for ignore_path in ignore_paths
                for inode_path in inode_to_paths.get(node.inode, frozenset())
            )
        ]),
    )


def label_nodes(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: CompressedDataflowGraph,
        inode_to_path: Map[ptypes.Inode, It[pathlib.Path]],
        max_args: int = 5,
        max_arg_length: int = 80,
        max_path_interval_length: int = 20,
        max_paths_per_inode: int = 2,
        max_inodes_per_set: int = 5,
        relative_to: pathlib.Path | None = None,
) -> None:
    count = dict[tuple[ptypes.Pid, ptypes.ExecNo], int]()
    root_pid = probe_log.get_root_pid()
    if networkx.is_directed_acyclic_graph(dataflow_graph):
        nodes = list(networkx.topological_sort(dataflow_graph))
        cycle = []
    else:
        nodes = list(dataflow_graph.nodes())
        cycle = list(networkx.find_cycle(dataflow_graph))
        warnings.warn(ptypes.UnusualProbeLog(
            "Dataflow graph contains a cycle (marked in red).",
        ))
    for node in nodes:
        data = dataflow_graph.nodes(data=True)[node]
        match node:
            case ProcessState():
                data["shape"] = "oval"
                data["cluster"] = f"Process {node.pid}"
                if node.pid == root_pid and node.epoch_no == 0 and node.deduplicator == 0:
                    data["label"] = "root"
                elif node.epoch_no != 0 and node.deduplicator == 0:
                    init_exec_epoch_quad = ptypes.OpQuad(node.pid, node.epoch_no, node.pid.main_thread(), 0)
                    init_exec_epoch = probe_log.get_op(init_exec_epoch_quad).data
                    assert isinstance(init_exec_epoch, ops.InitExecEpochOp)
                    data["label"] = "exec " + " ".join(
                        textwrap.shorten(
                            arg.decode(errors="backslashreplace"),
                            width=max_arg_length,
                        )
                        for arg in init_exec_epoch.argv[:max_args]
                    )
                else:
                    data["label"] = ""
            case ptypes.OpQuad():
                data["shape"] = "oval"
                op = probe_log.get_op(node)
                if node.op_no == 0:
                    count[(node.pid, node.exec_no)] = 1
                    if node.exec_no != 0:
                        assert isinstance(op.data, ops.InitExecEpochOp)
                        args = " ".join(
                            textwrap.shorten(
                                arg.decode(errors="backslashreplace"),
                                width=max_arg_length,
                            )
                            for arg in op.data.argv[:max_args]
                        )
                        if len(op.data.argv) > max_args:
                            args += "..."
                        data["label"] = f"exec {args}"
                    elif node.pid == root_pid:
                        data["label"] = "Root process"
                    else:
                        data["label"] = ""
                else:
                    data["label"] = ""
                    if (node.pid, node.exec_no) not in count:
                        warnings.warn(ptypes.UnusualProbeLog(
                            f"{node.pid, node.exec_no} never counted before",
                        ))
                        count[(node.pid, node.exec_no)] = 99
                    count[(node.pid, node.exec_no)] += 1
                    # data["label"] += "\n" + type(op.data).__name__
                data["id"] = str(node)
                data["cluster"] = f"Process {node.pid}"
            case frozenset():
                def shorten_path(input: pathlib.Path) -> str:
                    if input.is_absolute() and relative_to and input.is_relative_to(relative_to):
                        parts = input.parts[len(relative_to.parts):]
                        if len(parts) > 1:
                            input = pathlib.Path(parts[0]).joinpath(*parts[1:])
                        else:
                            input = pathlib.Path(".")
                    return ("/" if input.is_absolute() else "") + "/".join(
                        textwrap.shorten(part, width=max_path_interval_length)
                        for part in input.parts
                        if part != "/"
                    )
                inode_versions = list(node)
                inode_labels = []
                for inode_version in inode_versions[:max_inodes_per_set]:
                    inode_label = []
                    paths = inode_to_path.get(inode_version.inode, frozenset[pathlib.Path]())
                    for path in sorted(set(paths), key=lambda path: len(str(path)))[:max_paths_per_inode]:
                        inode_label.append(shorten_path(path))
                    inode_labels.append("\n".join(inode_label).strip() + f" v{inode_version.version}")
                if len(inode_versions) > max_inodes_per_set:
                    inode_labels.append("...other inodes")
                data["label"] = "\n".join(inode_labels)
                data["shape"] = "rectangle"
                data["id"] = str(hash(node))
    for a, b in cycle:
        dataflow_graph.edges[a, b]["color"] = "red"
