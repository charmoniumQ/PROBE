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
import networkx
import tqdm
from . import graph_utils
from . import ops
from . import ptypes


@dataclasses.dataclass(frozen=True)
class InodeVersionNode:
    """A particular version of the inode"""
    inode: ptypes.Inode
    version: int

    def __str__(self) -> str:
        return f"{self.inode} version {self.version}"


@dataclasses.dataclass(frozen=True)
class ProcessState:
    init_exec_epoch_quad: ptypes.OpQuad
    pid: ptypes.Pid
    epoch_no: ptypes.ExecNo
    deduplicator: int


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuad | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[ProcessState | frozenset[InodeVersionNode]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph


It: typing.TypeAlias = collections.abc.Iterable
Map: typing.TypeAlias = collections.abc.Mapping
Seq: typing.TypeAlias = collections.abc.Sequence
SegmentInfo: typing.TypeAlias = tuple[ptypes.AccessMode, ptypes.InodeVersion, graph_utils.Segment[ptypes.OpQuad]]


def _retain_pred(node: ptypes.OpQuad, op: ops.Op) -> bool:
    return isinstance(
        op.data,
        (ops.OpenOp, ops.CloseOp, ops.DupOp, ops.ExecOp, ops.ChdirOp, ops.InitExecEpochOp, ops.WaitOp, ops.MkFileOp),
    ) and getattr(op.data, "ferrno", 0) == 0


def hb_graph_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        hb_reachability_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
) -> tuple[DataflowGraph, Map[ptypes.Inode, It[pathlib.Path]]]:
    inode_segment_infos, inode_to_paths = find_segments(probe_log, hbg, hb_reachability_oracle)
    dataflow_graph = typing.cast(DataflowGraph, hbg.copy())
    n_segments = sum(map(len, inode_segment_infos.values()))
    n_inodes = len(inode_segment_infos.values())
    with charmonium.time_block.ctx(
            f"add {n_segments} segments for {n_inodes} inodes", print_start=False
    ):
        for inode, segments in inode_segment_infos.items():
            ordered_segments = order_segments(segments)
            print_segments(probe_log, inode, inode_to_paths, ordered_segments)
            add_inode_segments(dataflow_graph, inode, ordered_segments)
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
        reachability_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
) -> tuple[Map[ptypes.Inode, Seq[SegmentInfo]], Map[ptypes.Inode, Seq[pathlib.Path]]]:
    inode_to_segments = collections.defaultdict[ptypes.Inode, list[SegmentInfo]](list)
    cwds = dict[ptypes.Pid, pathlib.Path]()
    inode_to_paths = collections.defaultdict[ptypes.Inode, list[pathlib.Path]](list)

    fallback_quad = list(networkx.topological_sort(hb_graph))[-1]

    quads = graph_utils.topological_sort_depth_first(hb_graph, score_children=_score_children)
    for quad in tqdm.tqdm(quads, total=len(hb_graph), desc="Ops -> segments"):
        assert quad is not None
        op_data = probe_log.get_op(quad).data
        match op_data:
            case ops.InitExecEpochOp():
                cwds[quad.pid] = _to_path(cwds, inode_to_paths, quad, op_data.cwd)
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.exe)
                segment = reachability_oracle.segment(frozenset({quad}), frozenset({quad}))
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
                closes = find_closes(
                    probe_log,
                    reachability_oracle,
                    hb_graph,
                    quad,
                    op_data.fd,
                    bool(op_data.flags & os.O_CLOEXEC),
                    inode_version,
                    fallback_quad,
                )
                closes = reachability_oracle.get_bottommost(closes)
                access = ptypes.AccessMode.from_open_flags(op_data.flags)
                segment = reachability_oracle.segment(frozenset({quad}), closes)
                inode_to_segments[inode_version.inode].append((access, inode_version, segment))
                path = _to_path(cwds, inode_to_paths, quad, op_data.path)
                inode_to_paths[inode_version.inode].append(path)
        assert quads.send(True) is None
    return inode_to_segments, inode_to_paths


def find_closes(
        probe_log: ptypes.ProbeLog,
        reachability_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        hb_graph: ptypes.HbGraph,
        initial_quad: ptypes.OpQuad,
        initial_fd: int,
        initial_cloexec: bool,
        inode_version: ptypes.InodeVersion,
        fallback_quad: ptypes.OpQuad,
) -> frozenset[ptypes.OpQuad]:
    fds_to_watch = collections.defaultdict[ptypes.Pid, set[int]](set)
    fds_to_watch[initial_quad.pid].add(initial_fd)
    cloexecs = {initial_quad.pid: {initial_fd: initial_cloexec}}
    closes = set[ptypes.OpQuad]()
    quads = graph_utils.topological_sort_depth_first(
        hb_graph,
        initial_quad,
        _score_children,
        reachability_oracle,
    )
    # Iterate past the initial quad
    assert quads.send(None) == initial_quad
    assert quads.send(True) is None
    print("Searching for", fds_to_watch)
    for quad in quads:
        assert quad is not None
        assert reachability_oracle.is_reachable(initial_quad, quad)
        op_data = probe_log.get_op(quad).data
        print(quad, op_data.__class__.__name__, fds_to_watch)
        match op_data:
            case ops.OpenOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    print("Pruned")
                    assert quads.send(False) is None
                    continue
            case ops.ExecOp():
                print("Exec")
                for fd in fds_to_watch[quad.pid]:
                    if cloexecs[quad.pid][fd]:
                        print("Cloexec", fd)
                        closes.add(quad)
                        fds_to_watch[quad.pid].remove(fd)
            case ops.CloseOp():
                if op_data.fd in fds_to_watch[quad.pid]:
                    if ptypes.InodeVersion.from_probe_path(op_data.path).inode == inode_version.inode:
                        closes.add(quad)
                        fds_to_watch[quad.pid].remove(op_data.fd)
                    else:
                        print("Pruned")
                        assert quads.send(False) is None
                        continue
            case ops.DupOp():
                if op_data.old in fds_to_watch[quad.pid]:
                    if ptypes.InodeVersion.from_probe_path(op_data.path).inode == inode_version.inode:
                        fds_to_watch[quad.pid].add(op_data.new)
                        cloexecs[quad.pid][op_data.new] = bool(op_data.flags & os.O_CLOEXEC)
                        print("Dup", fds_to_watch)
                    else:
                        print("Pruned")
                        assert quads.send(False) is None
                        continue
            case ops.CloneOp():
                if op_data.task_type == ptypes.TaskType.TASK_PID:
                    target = ptypes.Pid(op_data.task_id)
                    if op_data.flags & os.CLONE_FILES:
                        fds_to_watch[target] = fds_to_watch[quad.pid]
                        cloexecs[target] = cloexecs[quad.pid]
                    else:
                        fds_to_watch[target] = {*fds_to_watch[quad.pid]}
                        cloexecs[target] = {**cloexecs[quad.pid]}

        print("Here")
        if not any(
            successor.pid == quad.pid
            for successor in hb_graph.successors(quad)
        ):
            print("Last")
            # last quad in this process
            for fd in fds_to_watch[quad.pid]:
                closes.add(quad)
            fds_to_watch[quad.pid].clear()
        else:
            print("Successors", [
                successor
                for successor in hb_graph.successors(quad)
                if successor.pid == quad.pid
            ])

        if not fds_to_watch[quad.pid]:
            print("No active FDs left; pruned")
            assert quads.send(False) is None
        else:
            assert quads.send(True) is None

    if any(fds_to_watch.values()):
        fds_to_watch_filtered = {
            pid: fds
            for pid, fds in fds_to_watch.items()
            if fds
        }
        warnings.warn(ptypes.UnusualProbeLog(f"We don't know where {fds_to_watch_filtered} got closed."))
        closes.add(fallback_quad)
    return frozenset(closes)


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
        dataflow_graph: DataflowGraph,
        inode: ptypes.Inode,
        ordered_segments: It[It[SegmentInfo]],
        pre_existing: bool = True, # TODO: Make mkfifo and mktemp turn pre_existing to False
) -> None:
    version = 0 if pre_existing else None
    for concurrent_segments in ordered_segments:
        write_onlies = frozenset([
            segment
            for segment in concurrent_segments
            if segment[0].is_write and segment[0] != ptypes.AccessMode.READ_WRITE
        ])
        read_onlies = frozenset([
            segment
            for segment in concurrent_segments
            if segment[0].is_read and segment[0] != ptypes.AccessMode.READ_WRITE
        ])
        read_writes = frozenset([
            segment
            for segment in concurrent_segments
            if segment[0] == ptypes.AccessMode.READ_WRITE
        ])

        possible_versions: list[int] = [version] if version is not None else []

        # Reads in the same generation as a write may (or may not) access the output of the write.
        # possible_versions will hold the versions that MAY be accessed.
        # writes will go first, and populate possible_versions with version+1, then reads.

        # As written, read_write would create a loop,
        # since it can write version N+1 at the bottom of its interval, but read N+1 at the top of its interval.
        # Therefore, we handle it specially.
        # A read_write CAN read the output of writes, but only of other non-READ_WRITE writes.

        if write_onlies:
            next_version = 0 if version is None else version + 1
            for write_segment in write_onlies:
                for node in write_segment[2].lower_bound:
                    dataflow_graph.add_edge(node, InodeVersionNode(inode, next_version))
                    assert not networkx.is_directed_acyclic_graph(dataflow_graph)
                    if write_segment[0] != ptypes.AccessMode.TRUNCATE_WRITE:
                        for possible_version in possible_versions:
                            dataflow_graph.add_edge(
                                InodeVersionNode(inode, possible_version),
                                InodeVersionNode(inode, next_version),
                            )
                            assert not networkx.is_directed_acyclic_graph(dataflow_graph)
            version = next_version
            possible_versions.append(version)

        if read_writes:
            next_version = 0 if version is None else version + 1
            for rw_segment in read_writes:
                for node in rw_segment[2].upper_bound:
                    for possible_version in possible_versions:
                        dataflow_graph.add_edge(InodeVersionNode(inode, possible_version), node)
                        assert not networkx.is_directed_acyclic_graph(dataflow_graph)
                for node in rw_segment[2].lower_bound:
                    dataflow_graph.add_edge(node, InodeVersionNode(inode, next_version))
                    assert not networkx.is_directed_acyclic_graph(dataflow_graph)
            version = next_version
            possible_versions.append(version)

        if len(read_writes) > 1:
            warnings.warn(ptypes.UnusualProbeLog(
                f"Multiple READ_WRITE accesses to {inode}. "
                "Unlike pure READ and pure WRITE accesses, READ_WRITE accesses can communicate with each other, forming a cycle in the dataflow graph. "
                "Proceeding cautiously, avoiding the cycle by assuming there is no RW->RW communication."
            ))

        if inode.is_fifo:
            possible_versions = [possible_versions[-1]]

        if read_onlies:
            for read_segment in read_onlies:
                if not possible_versions:
                    warnings.warn(ptypes.UnusualProbeLog(f"Read of inode {inode} before it appears to exist"))
                    possible_versions = [0]
                for node in read_segment[2].upper_bound:
                    for version in possible_versions:
                        dataflow_graph.add_edge(InodeVersionNode(inode, version), node)
                        assert not networkx.is_directed_acyclic_graph(dataflow_graph)


@charmonium.time_block.decor(print_start=False)
def combine_indistinguishable_inodes(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        hb_reachability_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
    if not networkx.is_directed_acyclic_graph(dataflow_graph):
        warnings.warn(ptypes.UnusualProbeLog("Dataflow graph is cyclic"))
    n_ops = sum(
        isinstance(node, ptypes.OpQuad)
        for node in dataflow_graph.nodes()
    )
    dataflow_graph2 = combine_adjacent_ops(probe_log, hbg, hb_reachability_oracle, dataflow_graph)
    n_ops2 = sum(
        isinstance(node, ptypes.OpQuad)
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
        isinstance(node, InodeVersionNode)
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
        hb_reachability_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
) -> networkx.DiGraph[ProcessState | InodeVersionNode]:
    combined_dataflow_graph: networkx.DiGraph[ProcessState | InodeVersionNode] = networkx.DiGraph()
    quad_to_state = {}
    edges: list[tuple[ptypes.OpQuad | ProcessState, ptypes.OpQuad | ProcessState]] = []
    for pid, process in probe_log.processes.items():
        for exec_epoch, exec in process.execs.items():
            init_exec_epoch_quad = ptypes.OpQuad(pid, exec_epoch, pid.main_thread(), 0)
            assert isinstance(probe_log.get_op(init_exec_epoch_quad).data, ops.InitExecEpochOp)
            for deduplicator, (inputs, outputs, quads) in enumerate(get_read_write_batches(
                    hbg,
                    hb_reachability_oracle,
                    dataflow_graph,
                    pid,
                    exec,
            )):
                state = ProcessState(init_exec_epoch_quad, pid, exec.exec_no, deduplicator)
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
    for src, dst in edges:
        src_state = quad_to_state[src] if isinstance(src, ptypes.OpQuad) else src
        dst_state = quad_to_state[dst] if isinstance(dst, ptypes.OpQuad) else dst
        combined_dataflow_graph.add_edge(src_state, dst_state)
    return combined_dataflow_graph


def _dataflow_outputs(dataflow_graph: DataflowGraph, quad: ptypes.OpQuad) -> list[ptypes.OpQuad | InodeVersionNode]:
    return [
        output
        for output in dataflow_graph.successors(quad)
        if isinstance(output, InodeVersionNode) or output.pid != quad.pid or output.exec_no != quad.exec_no
    ]


def _dataflow_inputs(dataflow_graph: DataflowGraph, quad: ptypes.OpQuad) -> list[ptypes.OpQuad | InodeVersionNode]:
    return [
        input
        for input in dataflow_graph.predecessors(quad)
        if isinstance(input, InodeVersionNode) or input.pid != quad.pid or input.exec_no != quad.exec_no
    ]


def get_read_write_batches(
        hbg: ptypes.HbGraph,
        hb_reachability_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        dataflow_graph: DataflowGraph,
        pid: ptypes.Pid,
        exec: ptypes.Exec,
) -> typing.Iterator[tuple[
    typing.Iterable[ptypes.OpQuad | InodeVersionNode],
    typing.Iterable[ptypes.OpQuad | InodeVersionNode],
    typing.Iterable[ptypes.OpQuad],
]]:
    """Get read and write epochs.

    E.g., all the reads done by the process up until a write, then all the writes done by the process.

    """
    main_thread = exec.threads[pid.main_thread()]
    first_quad = ptypes.OpQuad(pid, exec.exec_no, pid.main_thread(), 0)
    last_quad = ptypes.OpQuad(pid, exec.exec_no, pid.main_thread(), len(main_thread.ops) - 1)
    queue: dict[int, set[ptypes.OpQuad]] = collections.defaultdict(set, [(0, {first_quad})])
    queue_inverse = {first_quad: 0}
    reading_mode = True # else writing_mode
    inputs = []
    outputs = []
    incorporated_quads = set()
    while queue[0]:
        progress = True
        # We have to progress in order to keep looping
        while progress:
            progress = False
            for quad in list(queue[0]):
                if not hb_reachability_oracle.is_reachable(quad, last_quad):
                    # Not related to us, and neither are the descendents
                    # Toss in the bin
                    queue[0].remove(quad)
                    del queue_inverse[quad]
                    continue
                elif (quad.pid != pid or quad.exec_no != exec.exec_no):
                    # Not related to us, but the descendents are
                    # Toss in the bin, but add descendants
                    queue[0].remove(quad)
                    del queue_inverse[quad]
                elif quad not in dataflow_graph.nodes():
                    # No dataflow connections, but it could still be pointed to.
                    incorporated_quads.add(quad)
                    queue[0].remove(quad)
                    del queue_inverse[quad]
                elif (
                        (reading_mode and len(_dataflow_outputs(dataflow_graph, quad)) == 0) or
                        (not reading_mode and len(_dataflow_inputs(dataflow_graph, quad)) == 0)):
                    # In the process, up next, in the right mode
                    # Remove, process, add children
                    incorporated_quads.add(quad)
                    queue[0].remove(quad)
                    del queue_inverse[quad]
                    if reading_mode:
                        inputs.extend(_dataflow_inputs(dataflow_graph, quad))
                    else:
                        outputs.extend(_dataflow_outputs(dataflow_graph, quad))
                else:
                    # In the right process, but not the right mode
                    # Leave in the queue
                    continue

                for successor in hbg.successors(quad):
                    if successor in queue_inverse:
                        in_degree = queue_inverse[successor]
                        assert in_degree - 1 >= 0
                        queue_inverse[successor] = in_degree - 1
                        queue[in_degree].remove(successor)
                        queue[in_degree - 1].add(successor)
                        progress = progress or in_degree == 0
                    else:
                        in_degree = hb_reachability_oracle.n_paths(first_quad, successor) - 1
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
        max_path_segment_length: int = 20,
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
                    init_exec_epoch = probe_log.get_op(node.init_exec_epoch_quad).data
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
                        textwrap.shorten(part, width=max_path_segment_length)
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


def print_segments(
        probe_log: ptypes.ProbeLog,
        inode: ptypes.Inode,
        inode_to_paths: Map[ptypes.Inode, It[pathlib.Path]],
        ordered_segments: It[It[SegmentInfo]],
) -> None:
    indent = 0
    print("Segments for inode: ", inode)
    for path in set(inode_to_paths.get(inode, [])):
        indent = 1
        print(" " * indent, path)
    for concurrent_segments in ordered_segments:
        indent = 1
        length = len(list(concurrent_segments))
        print(" " * indent, f"{length} concurrent segments:")
        for access, inv, segment in concurrent_segments:
            indent = 3
            print(" " * indent, access)
            if segment.upper_bound != segment.lower_bound or len(segment.upper_bound) != 1:
                indent = 5
                bound = list(segment.upper_bound)
                quad = bound[0]
                op = probe_log.get_op(quad).data
                print(" " * indent, f"starting at {quad} {str(op)[:100]}")
                for quad in bound[1:]:
                    op = probe_log.get_op(quad).data
                    print(" " * indent, f"or {quad} {str(op)[:100]}")
                bound = list(segment.lower_bound)
                quad = bound[0]
                op = probe_log.get_op(quad).data
                print(" " * indent, f"ending at {quad} {str(op)[:100]}")
                for quad in bound[1:]:
                    op = probe_log.get_op(quad).data
                    print(" " * indent, f"or {quad} {str(op)[:100]}")
            else:
                bound = list(segment.upper_bound)
                quad = bound[0]
                op = probe_log.get_op(quad).data
                print(" " * indent, f"atomically at {quad} {str(op)[:100]}")
