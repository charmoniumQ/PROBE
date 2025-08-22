from __future__ import annotations
import collections
import dataclasses
import fnmatch
import functools
import itertools
import os
import pathlib
import textwrap
import typing
import warnings
import charmonium.time_block
import networkx
from . import hb_graph
from . import graph_utils
from . import ops
from . import ptypes


_Node = typing.TypeVar("_Node")


@dataclasses.dataclass(frozen=True)
class InodeVersionNode:
    """A particular version of the inode"""
    inode: ptypes.Inode
    version: int

    def __str__(self) -> str:
        return f"{self.inode} version {self.version}"


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuad | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuad | frozenset[InodeVersionNode]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph


SegmentInfo: typing.TypeAlias = tuple[ptypes.AccessMode, ptypes.InodeVersion, graph_utils.Segment[ptypes.OpQuad]]

def _retain_pred(node: ptypes.OpQuad, op: ops.Op) -> bool:
    return isinstance(
        op.data,
        (ops.OpenOp, ops.CloseOp, ops.DupOp, ops.ExecOp, ops.ChdirOp, ops.InitExecEpochOp),
    ) and getattr(op.data, "ferrno", 0) == 0


def hb_graph_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
) -> tuple[DataflowGraph, collections.abc.Mapping[ptypes.Inode, list[pathlib.Path]]]:
    hbg = hb_graph.retain_only(probe_log, hbg, _retain_pred)
    reachability_oracle = graph_utils.PrecomputedReachabilityOracle.create(hbg)
    inode_segment_infos, inodes_to_paths = find_segments(probe_log, reachability_oracle, hbg)
    dataflow_graph = typing.cast(DataflowGraph, hbg.copy())
    for inode, segment_infos in inode_segment_infos.items():
        add_segments(dataflow_graph, inode, segment_infos)
    return dataflow_graph, inodes_to_paths


def _score_children(parent: ptypes.OpQuad, child: ptypes.OpQuad) -> int:
    return 0 if parent.tid == child.tid else 1 if parent.pid == child.pid else 2 if parent.pid <= child.pid else 3


def find_segments(
        probe_log: ptypes.ProbeLog,
        reachability_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        hb_graph: ptypes.HbGraph,
) -> tuple[collections.abc.Mapping[ptypes.Inode, list[SegmentInfo]], collections.abc.Mapping[ptypes.Inode, list[pathlib.Path]]]:
    inode_to_segments = collections.defaultdict[ptypes.Inode, list[SegmentInfo]](list)
    cwds = dict[ptypes.Pid, pathlib.Path]()
    inodes_to_paths = collections.defaultdict[ptypes.Inode, list[pathlib.Path]](list)

    def record_path(quad: ptypes.OpQuad, path: ops.Path) -> pathlib.Path:
        path_arg = pathlib.Path(path.path.decode())
        inode = ptypes.InodeVersion.from_probe_path(path).inode
        if path_arg:
            if quad.pid in cwds:
                return cwds[quad.pid] / path_arg
            elif path_arg.is_absolute():
                return path_arg
            else:
                warnings.warn(ptypes.UnusualProbeLog(f"Unkonwn cwd at quad {quad}; Did we not see InitExecEpoch?"))
        elif inode in inodes_to_paths:
            return inodes_to_paths[inode][-1]
        else:
            warnings.warn(ptypes.UnusualProbeLog(f"Unkonwn path for inode {inode} at quad {quad}"))
            return pathlib.Path()

    quads = graph_utils.topological_sort_depth_first(hb_graph, score_children=_score_children)
    for quad in quads:
        assert quad is not None
        op_data = probe_log.get_op(quad).data
        match op_data:
            case ops.InitExecEpochOp():
                cwds[quad.pid] = record_path(quad, op_data.cwd)
            case ops.ChdirOp():
                cwds[quad.pid] = record_path(quad, op_data.path)
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
                )
                closes = reachability_oracle.get_bottommost(closes)
                access = ptypes.AccessMode.from_open_flags(op_data.flags)
                segment = reachability_oracle.segment(frozenset({quad}), closes)
                inode_to_segments[inode_version.inode].append((access, inode_version, segment))
                inodes_to_paths[inode_version.inode].append(record_path(quad, op_data.path))
            case ops.ExecOp():
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.path)
                segment = reachability_oracle.segment(frozenset({quad}), frozenset({quad}))
                inode_to_segments[inode_version.inode].append((ptypes.AccessMode.EXEC, inode_version, segment))
                inodes_to_paths[inode_version.inode].append(record_path(quad, op_data.path))
            case ops.SpawnOp():
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.exec.path)
                segment = reachability_oracle.segment(frozenset({quad}), frozenset({quad}))
                inode_to_segments[inode_version.inode].append((ptypes.AccessMode.EXEC, inode_version, segment))
                inodes_to_paths[inode_version.inode].append(record_path(quad, op_data.exec.path))
        assert quads.send(True) is None
    return inode_to_segments, inodes_to_paths


def find_closes(
        probe_log: ptypes.ProbeLog,
        reachability_oracle: graph_utils.ReachabilityOracle[ptypes.OpQuad],
        hb_graph: ptypes.HbGraph,
        initial_node: ptypes.OpQuad,
        initial_fd: int,
        initial_cloexec: bool,
        inode_version: ptypes.InodeVersion,
) -> frozenset[ptypes.OpQuad]:
    fds_to_watch = collections.defaultdict[ptypes.Pid, set[int]](set)
    fds_to_watch[initial_node.pid].add(initial_fd)
    cloexecs = {initial_node.pid: {initial_fd: initial_cloexec}}
    closes = set[ptypes.OpQuad]()
    degree_func = functools.partial(reachability_oracle.n_paths, initial_node)
    nodes = graph_utils.topological_sort_depth_first(hb_graph, initial_node, _score_children, degree_func)
    for node in nodes:
        assert node is not None
        op_data = probe_log.get_op(node).data
        match op_data:
            case ops.OpenOp():
                if op_data.fd in fds_to_watch[node.pid]:
                    assert nodes.send(False) is None
                    continue
            case ops.ExecOp():
                for fd in fds_to_watch[node.pid]:
                    if cloexecs[node.pid][fd]:
                        closes.add(node)
                        fds_to_watch[node.pid].remove(fd)
            case ops.CloseOp():
                if op_data.fd in fds_to_watch[node.pid]:
                    if ptypes.InodeVersion.from_probe_path(op_data.path).inode == inode_version.inode:
                        closes.add(node)
                        fds_to_watch[node.pid].remove(fd)
                    else:
                        assert nodes.send(False) is None
                        continue
            case ops.DupOp():
                if op_data.old in fds_to_watch[node.pid]:
                    if ptypes.InodeVersion.from_probe_path(op_data.path).inode == inode_version.inode:
                        fds_to_watch[node.pid].add(op_data.new)
                    else:
                        assert nodes.send(False) is None
                        continue
            case ops.CloneOp():
                if op_data.task_type == ptypes.TaskType.TASK_PID:
                    target = ptypes.Pid(op_data.task_id)
                    if op_data.flags & os.CLONE_FILES:
                        fds_to_watch[target] = fds_to_watch[node.pid]
                        cloexecs[target] = cloexecs[node.pid]
                    else:
                        fds_to_watch[target] = {*fds_to_watch[node.pid]}
                        cloexecs[target] = {**cloexecs[node.pid]}
        if not fds_to_watch[node.pid]:
            assert nodes.send(False) is None
        else:
            assert nodes.send(True) is None
    if any(fds_to_watch.values()):
        assert node is not None
        closes.add(node)
        fds_to_watch_filtered = {
            pid: fds
            for pid, fds in fds_to_watch.items()
            if fds
        }
        warnings.warn(ptypes.UnusualProbeLog(f"We don't know where {fds_to_watch_filtered} got closed."))
    return frozenset(closes)


def add_segments(
        dataflow_graph: DataflowGraph,
        inode: ptypes.Inode,
        segment_infos: list[SegmentInfo],
) -> None:
    segment_hb: networkx.DiGraph[SegmentInfo] = networkx.DiGraph()
    segment_hb.add_nodes_from(segment_infos)
    for s0, s1 in itertools.permutations(segment_infos, 2):
        if s0[2].all_greater_than(s1[2]):
            segment_hb.add_edge(s0, s1)

    version = 0
    for segments in networkx.topological_generations(segment_hb):
        was_written = False
        # If reads and writes are concurrent, the "worst case" is that all the writes influence all the reads.
        for (access, inode_version, segment) in segments:
            if access.has_output:
                was_written = True
                # If there is a write, the "worst case" is that the very bottom nodes of the segment do the write.
                for node in segment.lower_bound:
                    dataflow_graph.add_edge(node, InodeVersionNode(inode, version))
                    if access.is_mutation:
                        dataflow_graph.add_edge(InodeVersionNode(inode, version - 1), InodeVersionNode(inode, version))
        if was_written:
            version += 1
        for (access, inode_version, segment) in segments:
            if access.has_input:
                # If there is a read, the "worst case" is that the very uppermost nodes of the segment do the read.
                for node in segment.upper_bound:
                    dataflow_graph.add_edge(InodeVersionNode(inode, version), node)


@charmonium.time_block.decor()
def combine_indistinguishable_inodes(
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
    if networkx.is_directed_acyclic_graph(dataflow_graph):
        with charmonium.time_block.ctx("transitive reduction"):
            dataflow_graph = networkx.transitive_reduction(dataflow_graph)
    else:
        warnings.warn(ptypes.UnusualProbeLog("Dataflow graph is cyclic"))
    ret = graph_utils.combine_structurally_equivalent(dataflow_graph, lambda node: isinstance(node, InodeVersionNode))
    print(f"Reduced dataflow_graph from {len(dataflow_graph)} nodes to {len(ret)} nodes by distinguishability")
    return typing.cast(CompressedDataflowGraph, ret)


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
        inode_to_paths: collections.abc.Mapping[ptypes.Inode, collections.abc.Iterable[pathlib.Path]],
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
        inodes_to_path: collections.abc.Mapping[ptypes.Inode, collections.abc.Iterable[pathlib.Path]],
        max_args: int = 5,
        max_arg_length: int = 80,
        max_path_segment_length: int = 20,
        max_paths_per_inode: int = 1,
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
                    inode_label.append(f"{inode_version.inode} v{inode_version.version}")
                    paths = inodes_to_path.get(inode_version.inode, frozenset[pathlib.Path]())
                    for path in sorted(paths, key=lambda path: len(str(path)))[:max_paths_per_inode]:
                        inode_label.append(shorten_path(path))
                    inode_labels.append("\n".join(inode_label))
                if len(inode_versions) > max_inodes_per_set:
                    inode_labels.append("...other inodes")
                data["label"] = "\n".join(inode_labels)
                data["shape"] = "rectangle"
                data["id"] = str(hash(node))
    for a, b in cycle:
        dataflow_graph.edges[a, b]["color"] = "red"
