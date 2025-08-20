from __future__ import annotations
import tqdm
import collections
import dataclasses
import enum
import os
import pathlib
import textwrap
import typing
import warnings
import networkx
from . import graph_utils
from . import hb_graph
from .hb_graph_accesses import hb_graph_to_accesses, Access, AccessMode, Phase
from . import ops
from . import ptypes


_Node = typing.TypeVar("_Node")


@dataclasses.dataclass(frozen=True)
class AccessEpoch[_Node]:
    """An access epoch is a set of nodes, denoted by a segment, in which the node may be accessed."""
    mode: AccessMode
    bounds: graph_utils.Segment[_Node]
    version: int | None = None


@dataclasses.dataclass(frozen=True)
class ExecNode:
    """An exec, denoted by Pid and ExecNo"""
    pid: ptypes.Pid
    exec_no: ptypes.ExecNo


@dataclasses.dataclass(frozen=True)
class InodeVersionNode:
    """A particular version of the inode"""
    inode: ptypes.Inode
    version: int

    def __str__(self) -> str:
        return f"{self.inode} version {self.version}"


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[hb_graph.OpNode | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[hb_graph.OpNode | frozenset[InodeVersionNode]]
    EpochGraph: typing.TypeAlias = networkx.DiGraph[AccessEpoch[hb_graph.OpNode]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph
    EpochGraph = networkx.DiGraph


def accesses_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        accesses_and_nodes: list[Access | hb_graph.OpNode],
) -> tuple[DataflowGraph, typing.Mapping[ptypes.Inode, frozenset[pathlib.Path]]]:
    """Turn a list of accesses into a dataflow graph, by assigning a version at every access."""

    class PidState(enum.IntEnum):
        READING = enum.auto()
        WRITING = enum.auto()

    parent_pid = probe_log.get_parent_pid_map()
    pid_to_state = collections.defaultdict[ptypes.Pid, PidState](lambda: PidState.READING)
    last_op_in_process = dict[ptypes.Pid, hb_graph.OpNode]()
    inode_to_version = collections.defaultdict[ptypes.Inode, int](lambda: 0)
    inode_to_paths = collections.defaultdict[ptypes.Inode, set[pathlib.Path]](set)
    dataflow_graph = DataflowGraph()

    def add_node(node: hb_graph.OpNode) -> None:
        pid_to_state[node.pid] = PidState.READING
        if program_order_predecessor := last_op_in_process.get(node.pid):
            dataflow_graph.add_edge(program_order_predecessor, node)
        else:
            if parent := parent_pid.get(node.pid):
                dataflow_graph.add_edge(last_op_in_process[parent], node)
            else:
                pass
                # Found initial node of root proc
        last_op_in_process[node.pid] = node

    def ensure_state(node: hb_graph.OpNode, desired_state: PidState) -> None:
        if desired_state == PidState.WRITING and pid_to_state[node.pid] == PidState.READING:
            # Reading -> writing for free
            pid_to_state[node.pid] = PidState.WRITING
        elif desired_state == PidState.READING and pid_to_state[node.pid] == PidState.WRITING:
            # Writing -> reading by starting a new node.
            add_node(node)
        assert pid_to_state[node.pid] == desired_state

    for access_or_node in accesses_and_nodes:
        match access_or_node:
            case Access():
                access = access_or_node
                version_num = inode_to_version[access.inode]
                inode_to_paths[access.inode].add(access.path)
                version = InodeVersionNode(access.inode, version_num)
                next_version = InodeVersionNode(access.inode, version_num + 1)
                ensure_state(access.op_node, PidState.READING if access.mode.is_side_effect_free() else PidState.WRITING)
                if (op_node := last_op_in_process.get(access.op_node.pid)) is None:
                    warnings.warn(ptypes.UnusualProbeLog(f"Can't find last node from process {access.op_node.pid}"))
                    continue
                match access.mode:
                    case AccessMode.WRITE:
                        if access.phase == Phase.BEGIN:
                            dataflow_graph.add_edge(op_node, next_version)
                            dataflow_graph.add_edge(version, next_version)
                    case AccessMode.TRUNCATE_WRITE:
                        if access.phase == Phase.END:
                            dataflow_graph.add_edge(op_node, next_version)
                    case AccessMode.READ_WRITE:
                        if access.phase == Phase.BEGIN:
                            dataflow_graph.add_edge(version, op_node)
                        if access.phase == Phase.END:
                            dataflow_graph.add_edge(op_node, next_version)
                            dataflow_graph.add_edge(version, next_version)
                    case AccessMode.READ | AccessMode.EXEC | AccessMode.DLOPEN:
                        if access.phase == Phase.BEGIN:
                            dataflow_graph.add_edge(version, op_node)
                    case _:
                        raise TypeError()
            case hb_graph.OpNode():
                node = access_or_node
                op_data = probe_log.get_op(*node.op_quad()).data
                match op_data:
                    # us -> our child
                    # Therefore, we have to be in writing mode
                    case ops.CloneOp():
                        if op_data.task_type == ptypes.TaskType.TASK_PID and not (op_data.flags & os.CLONE_THREAD):
                            ensure_state(node, PidState.WRITING)
                    case ops.SpawnOp():
                        ensure_state(node, PidState.WRITING)
                    case ops.InitExecEpochOp():
                        add_node(node)
    inode_to_paths2 = {inode: frozenset(paths) for inode, paths in inode_to_paths.items()}
    return dataflow_graph, inode_to_paths2


def hb_graph_to_dataflow_graph2(
        probe_log: ptypes.ProbeLog,
        hbg: hb_graph.HbGraph,
        check: bool = False,
) -> tuple[DataflowGraph, typing.Mapping[ptypes.Inode, frozenset[pathlib.Path]]]:
    accesses = list(hb_graph_to_accesses(probe_log, hbg))
    dataflow_graph, paths = accesses_to_dataflow_graph(probe_log, accesses)
    if check:
        validate_dataflow_graph(probe_log, dataflow_graph)
    return dataflow_graph, paths


def combine_indistinguishable_inodes(
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
    if networkx.is_directed_acyclic_graph(dataflow_graph):
        dataflow_graph = networkx.transitive_reduction(dataflow_graph)
    else:
        warnings.warn(ptypes.UnusualProbeLog("Dataflow graph is cyclic"))
    def same_neighbors(
            node0: hb_graph.OpNode | InodeVersionNode,
            node1: hb_graph.OpNode | InodeVersionNode,
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
    def node_mapper(node_set: frozenset[hb_graph.OpNode | InodeVersionNode]) -> hb_graph.OpNode | frozenset[InodeVersionNode]:
        first_node = next(iter(node_set))
        if isinstance(first_node, hb_graph.OpNode):
            assert all(isinstance(node, hb_graph.OpNode) for node in node_set)
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
    for node in tqdm.tqdm(
            networkx.topological_sort(dataflow_graph),
            total=len(dataflow_graph),
            desc="Labelling DFG nodes",
    ):
        data = dataflow_graph.nodes(data=True)[node]
        match node:
            case hb_graph.OpNode():
                data["shape"] = "oval"
                op = probe_log.get_op(node.pid, node.exec_no, node.pid.main_thread(), 0)
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
                            f"{node.pid, node.exec_no} never counted before"
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
                    inode_label.append(f"{inode_version.inode.number} v{inode_version.version}")
                    paths = inodes_to_path.get(inode_version.inode, frozenset[pathlib.Path]())
                    for path in sorted(paths, key=lambda path: len(str(path)))[:max_paths_per_inode]:
                        inode_label.append(shorten_path(path))
                    inode_labels.append("\n".join(inode_label))
                if len(inode_versions) > max_inodes_per_set:
                    inode_labels.append("...other inodes")
                data["label"] = "\n".join(inode_labels)
                data["shape"] = "rectangle"
                data["id"] = str(hash(node))
