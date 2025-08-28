from __future__ import annotations
import collections
import dataclasses
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
from . import ops
from . import ptypes


It: typing.TypeAlias = collections.abc.Iterable
Map: typing.TypeAlias = collections.abc.Mapping
Seq: typing.TypeAlias = collections.abc.Sequence


@dataclasses.dataclass(frozen=True)
class InodeVersionNode:
    """A particular version of the inode"""
    inode: ptypes.Inode
    version: int
    deduplicator: tuple[int, int] | None = None

    def __str__(self) -> str:
        return f"{self.inode} version {self.version}"


@dataclasses.dataclass(frozen=True)
class ProcessState:
    pid: ptypes.Pid
    epoch_no: ptypes.ExecNo
    deduplicator: int


@dataclasses.dataclass(frozen=True)
class SegmentsPerProcess:
    segments: Map[ptypes.Pid, graph_utils.Segment[ptypes.OpQuad]]

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
        return SegmentsPerProcess(frozendict.frozendict({quad.pid: graph_utils.Segment.singleton(hb_oracle, quad)}))

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
        return SegmentsPerProcess(frozendict.frozendict(union_segments_per_process))


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuad | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[ProcessState | frozenset[InodeVersionNode]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph
SegmentInfo: typing.TypeAlias = tuple[ptypes.AccessMode, ptypes.InodeVersion, SegmentsPerProcess]


def _retain_pred(node: ptypes.OpQuad, op: ops.Op) -> bool:
    return isinstance(
        op.data,
        (ops.OpenOp, ops.CloseOp, ops.CloneOp, ops.DupOp, ops.ExecOp, ops.ChdirOp, ops.InitExecEpochOp, ops.WaitOp, ops.MkFileOp),
    ) and getattr(op.data, "ferrno", 0) == 0


def hb_graph_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
) -> tuple[DataflowGraph, Map[ptypes.Inode, It[pathlib.Path]]]:
    inode_segments, inode_to_paths = find_segments(probe_log, hbg, hb_oracle)
    dataflow_graph = typing.cast(DataflowGraph, hbg.copy())
    n_segments = sum(map(len, inode_segments.values()))
    n_inodes = len(inode_segments.values())
    with charmonium.time_block.ctx(
            f"add {n_segments} segments for {n_inodes} inodes", print_start=False
    ):
        for inode, segments in inode_segments.items():
            ordered_segments = order_segments(segments)
            version = 0
            for concurrent_segments in ordered_segments:
                version = add_inode_segments(hb_oracle, dataflow_graph, inode, concurrent_segments, version)
    return dataflow_graph, inode_to_paths


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
                inode_to_segments[inode_version.inode].append((ptypes.AccessMode.EXEC, inode_version, segment))
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
                inode_to_segments[inode_version.inode].append((access, inode_version, segment))
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
    print(f"  Searching for {fds_to_watch} {inode_version.inode}")
    for quad in quads:
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
                for fd in fds_to_watch[quad.pid]:
                    if cloexecs[quad.pid][fd]:
                        print(f"    Cloexec {fd}")
                        fds_to_watch[quad.pid].remove(fd)
                        if not fds_to_watch[quad.pid]:
                            closes[quad.pid].add(quad)
            case ops.CloseOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    if ptypes.InodeVersion.from_probe_path(op_data.path).inode == inode_version.inode:
                        print(f"    Close {op_data.fd}")
                        fds_to_watch[quad.pid].remove(op_data.fd)
                        if not fds_to_watch[quad.pid]:
                            closes[quad.pid].add(quad)
                    else:
                        print(f"    Subsequent close of a different {op_data.fd} pruned")
                        assert quads.send(False) is None
                        continue
                else:
                    print(f"    Close {op_data.fd} (unrelated)")
            case ops.DupOp():
                if op_data.old in fds_to_watch[quad.pid]:
                    if ptypes.InodeVersion.from_probe_path(op_data.path).inode == inode_version.inode:
                        fds_to_watch[quad.pid].add(op_data.new)
                        cloexecs[quad.pid][op_data.new] = bool(op_data.flags & os.O_CLOEXEC)
                        print(f"    Dup {op_data.old} -> {op_data.new} {fds_to_watch}")
                    else:
                        print(f"    Subsequent dup of a different {op.data.old} pruned")
                        assert quads.send(False) is None
                        continue
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
        raise ptypes.InvalidProbeLog(f"We don't know where {fds_to_watch_filtered} got closed.")

    assert opens.keys() == closes.keys()

    ret = SegmentsPerProcess(frozendict.frozendict({
        pid: graph_utils.Segment(hb_oracle, frozenset(opens[pid]), frozenset(closes[pid]))
        for pid in opens.keys()
    }))
    print(str(inode_version.inode), ret)
    return ret


def order_segments(
        segments: It[SegmentInfo]
) -> It[It[SegmentInfo]]:
    segment_hb: networkx.DiGraph[SegmentInfo] = networkx.DiGraph()
    segment_hb.add_nodes_from(segments)
    for s0, s1 in itertools.permutations(segments, 2):
        if s0[2].all_greater_than(s1[2]):
            segment_hb.add_edge(s0, s1)
    return list(networkx.topological_generations(segment_hb))


def add_inode_segments(
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
        inode: ptypes.Inode,
        concurrent_segments: It[SegmentInfo],
        version: int,
) -> int:
    print(f"  Concurrent segments for {inode} {version}")
    union_read_segments = SegmentsPerProcess.union(*[
        segment
        for access, _, segment in concurrent_segments
        if access.is_read
    ])
    union_write_segments = SegmentsPerProcess.union(*[
        segment
        for access, _, segment in concurrent_segments
        if access.is_write
    ])

    print(f"    Readers: {sorted(union_read_segments.segments.keys())}")
    print(f"    Writers: {sorted(union_write_segments.segments.keys())}")

    # Past writes -> current reads
    inode_version = InodeVersionNode(inode, version)
    for read_no, (read_process, read_segment) in enumerate(union_read_segments.segments.items()):
        for read_node in read_segment.upper_bound:
            dataflow_graph.add_edge(read_node, inode_version)

    # Current writes -> current reads
    if union_read_segments and union_write_segments:
        version += 1
        inode_version = InodeVersionNode(inode, version)
        for write_no, (write_process, write_segment) in enumerate(union_write_segments.segments.items()):
            for read_no, (read_process, read_segment) in enumerate(union_read_segments.segments.items()):
                if write_process != read_process:
                    for write_node in write_segment.lower_bound:
                        for read_node in read_segment.upper_bound:
                            dataflow_graph.add_edge(write_node, inode_version)
                            dataflow_graph.add_edge(inode_version, read_node)

    # Current writes -> future reads
    if union_write_segments:
        version += 1
        inode_version = InodeVersionNode(inode, version)
        for write_no, (write_process, write_segment) in enumerate(union_write_segments.segments.items()):
            for write_node in write_segment.lower_bound:
                dataflow_graph.add_edge(write_node, InodeVersionNode(inode, version))

    return version

@charmonium.time_block.decor(print_start=False)
def combine_indistinguishable_inodes(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        hb_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
    if not networkx.is_directed_acyclic_graph(dataflow_graph):
        warnings.warn(ptypes.UnusualProbeLog("Dataflow graph is cyclic"))
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
    n_inodes2 = sum(
        isinstance(node, frozenset)
        for node in dataflow_graph3.nodes()
    )
    print(f"Combined isomorphic inodes {n_inodes} -> {n_inodes2}")
    n_edges = len(dataflow_graph.edges())
    with charmonium.time_block.ctx("transitive reduction", print_start=False):
        if networkx.is_directed_acyclic_graph(dataflow_graph3):
            dataflow_graph4 = networkx.transitive_reduction(dataflow_graph3)
        else:
            warnings.warn(ptypes.UnusualProbeLog("Cannot do reduction on cyclic graph"))
            dataflow_graph4 = dataflow_graph3
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
            for deduplicator, (inputs, outputs, quads) in enumerate(get_read_write_batches_simple(
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
    reading_mode = True # else writing_mode
    inputs = []
    outputs = []
    incorporated_quads = set()
    last_queue_0 = frozenset[ptypes.OpQuad]()
    last_last_queue_0 = frozenset[ptypes.OpQuad]()

    #print(f"Coalescing {pid} {exec.exec_no}")

    while queue[0]:
        #print(f"  {reading_mode=}")

        # Detect if we are stuck in an infinite loop
        if queue[0] == last_last_queue_0:
            raise RuntimeError("No progress made")
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

                if (not hb_oracle.is_reachable(quad, last_quad)) and quad != last_quad and quad != first_quad:
                    # Not related to us, and neither are the descendents
                    # Toss in the bin
                    queue[0].remove(quad)
                    del queue_inverse[quad]
                    #print("    Not reachable; prune")
                    continue
                elif quad.pid != pid or quad.exec_no != exec.exec_no:
                    # Not related to us, but the descendents are
                    # Toss in the bin, but add descendants
                    queue[0].remove(quad)
                    del queue_inverse[quad]
                    #print("    Wrong pid; pop & still follow children")
                elif quad not in dataflow_graph.nodes():
                    # No dataflow connections, but it could still be pointed to.
                    incorporated_quads.add(quad)
                    queue[0].remove(quad)
                    del queue_inverse[quad]
                    #print("    Not in dataflow; pop & add children")
                elif dataflow_inputs and dataflow_outputs:
                    raise ptypes.InvalidProbeLog(
                        "Current coalescing algorithm can't handle a node with simultaneous dataflow inputs and dataflow outputs.\n"
                        f"{quad=}\n"
                        f"{dataflow_inputs=}\n"
                        f"{dataflow_outputs=}\n"
                    )
                elif (
                        (reading_mode and not dataflow_outputs) or
                        (not reading_mode and not dataflow_inputs)
                ):
                    # In the process, up next, in the right mode
                    # Remove, process, add children
                    incorporated_quads.add(quad)
                    queue[0].remove(quad)
                    del queue_inverse[quad]
                    if reading_mode:
                        inputs.extend(dataflow_inputs)
                    else:
                        outputs.extend(dataflow_outputs)
                    #print("    Correct mode; pop & add children")
                else:
                    # In the right process, but not the right mode
                    # Leave in the queue
                    #print("    Incorrect mode; skip for now")
                    continue

                #print("    Successors:")
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
                    progress = progress or in_degree == 0

        if reading_mode:
            reading_mode = False
        else:
            reading_mode = True
            yield tuple(inputs), tuple(outputs), frozenset(incorporated_quads)
            inputs.clear()
            outputs.clear()
            incorporated_quads.clear()


    if incorporated_quads:
        yield tuple(inputs), tuple(outputs), frozenset(incorporated_quads)
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
                    for path in sorted(paths, key=lambda path: len(str(path)))[:max_paths_per_inode]:
                        inode_label.append(shorten_path(path))
                    inode_labels.append("\n".join(inode_label).strip() + f" v{inode_version.version}")
                if len(inode_versions) > max_inodes_per_set:
                    inode_labels.append("...other inodes")
                if inode_version.inode.is_fifo:
                    inode_label.append("(fifo)")
                data["label"] = "\n".join(inode_labels)
                data["shape"] = "rectangle"
                data["id"] = str(hash(node))
    for a, b in cycle:
        dataflow_graph.edges[a, b]["color"] = "red"
