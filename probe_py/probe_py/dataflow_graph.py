from __future__ import annotations
import dataclasses
import pathlib
import textwrap
import typing
import warnings
import networkx
from . import graph_utils
from . import headers as ops
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
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuint | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[ptypes.OpQuint | frozenset[InodeVersionNode]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph


def hb_graph_to_dataflow_graph2(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
        check: bool = False,
) -> tuple[DataflowGraph, typing.Mapping[ptypes.Inode, frozenset[pathlib.Path]]]:
    return DataflowGraph(), {}


def combine_indistinguishable_inodes(
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
    if networkx.is_directed_acyclic_graph(dataflow_graph):
        dataflow_graph = networkx.transitive_reduction(dataflow_graph)
    else:
        warnings.warn(ptypes.UnusualProbeLog("Dataflow graph is cyclic"))
    def same_neighbors(
            node0: ptypes.OpQuad | InodeVersionNode,
            node1: ptypes.OpQuad | InodeVersionNode,
    ) -> bool:
        return (
            isinstance(node0, InodeVersionNode)
            and
            isinstance(node1, InodeVersionNode)
            and
            frozenset(dataflow_graph.predecessors(node0)) == frozenset(dataflow_graph.predecessors(node1))
            and
            frozenset(dataflow_graph.successors(node0)) == frozenset(dataflow_graph.successors(node1))
        )
    def node_mapper(node_set: frozenset[ptypes.OpQuint | InodeVersionNode]) -> ptypes.OpQuint | frozenset[InodeVersionNode]:
        first_node = next(iter(node_set))
        if isinstance(first_node, ptypes.OpQuint):
            assert all(isinstance(node, ptypes.OpQuint) for node in node_set)
            return first_node
        else:
            assert all(isinstance(node, InodeVersionNode) for node in node_set)
            return typing.cast(frozenset[InodeVersionNode], node_set)
    quotient = networkx.quotient_graph(dataflow_graph, same_neighbors)
    for _, data in quotient.nodes(data=True):
        del data["nnodes"]
        del data["density"]
        del data["graph"]
        del data["nedges"]
    for _, _, data in quotient.edges(data=True):
        del data["weight"]
    ret = graph_utils.map_nodes(node_mapper, quotient, False)
    return ret


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


def label_nodes(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: CompressedDataflowGraph,
        inodes_to_path: typing.Mapping[ptypes.Inode, frozenset[pathlib.Path]],
        max_args: int = 5,
        max_arg_length: int = 80,
        max_path_segment_length: int = 20,
        max_paths_per_inode: int = 1,
        max_inodes_per_set: int = 5,
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
                        assert isinstance(op.data, ops.InitExecEpoch)
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
