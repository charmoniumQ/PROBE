from __future__ import annotations
import tqdm
import collections
import copy
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
from . import ops
from . import ptypes


_Node = typing.TypeVar("_Node")


class AccessMode(enum.IntEnum):
    """In what way are we accessing the inode version?"""
    READ = enum.auto()
    WRITE = enum.auto()
    READ_WRITE = enum.auto()
    TRUNCATE_WRITE = enum.auto()

    @staticmethod
    def from_open_flags(flags: int) -> AccessMode:
        access_mode = flags & os.O_ACCMODE
        if access_mode == os.O_RDONLY:
            return AccessMode.READ
        elif flags & (os.O_TRUNC | os.O_CREAT):
            return AccessMode.TRUNCATE_WRITE
        elif access_mode == os.O_WRONLY:
            return AccessMode.WRITE
        elif access_mode == os.O_RDWR:
            return AccessMode.READ_WRITE
        else:
            raise ptypes.InvalidProbeLog(f"Invalid open flags: 0x{flags:x}")


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
    paths: frozenset[pathlib.Path] = frozenset({})

    def __str__(self) -> str:
        return f"{' '.join(map(str, self.paths))} {self.inode.number} v{self.version}"


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[hb_graph.OpNode | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[hb_graph.OpNode | frozenset[InodeVersionNode]]
    EpochGraph: typing.TypeAlias = networkx.DiGraph[AccessEpoch[hb_graph.OpNode]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph
    EpochGraph = networkx.DiGraph


@dataclasses.dataclass
class FileDescriptor:
    access_mode: AccessMode
    open_op: hb_graph.OpNode
    close_ops: list[hb_graph.OpNode]
    inode: ptypes.Inode
    cloexec: bool
    version: int


class PidState(enum.IntEnum):
    READING = enum.auto()
    WRITING = enum.auto()


class FdTable(collections.UserDict[int, FileDescriptor]):
    original_pid: ptypes.Pid


def hb_graph_to_dataflow_graph2(
        probe_log: ptypes.ProbeLog,
        hbg: hb_graph.HbGraph,
        check: bool = False,
) -> DataflowGraph:
    interesting_op_types = (ops.OpenOp, ops.CloseOp, ops.DupOp, ops.ExecOp, ops.SpawnOp, ops.InitExecEpochOp, ops.CloneOp)
    reduced_hb_graph = hb_graph.retain_only(
        probe_log,
        hbg,
        lambda node, op: isinstance(op.data, interesting_op_types) and getattr(op.data, "ferrno", 0) == 0,
    )

    pid_to_state = collections.defaultdict[ptypes.Pid, PidState](lambda: PidState.READING)
    last_op_in_process = dict[ptypes.Pid, hb_graph.OpNode]()
    proc_fd_to_fd = collections.defaultdict[ptypes.Pid, FdTable](lambda: FdTable())
    inode_to_version = collections.defaultdict[ptypes.Inode, int](lambda: 0)
    inode_to_paths = collections.defaultdict[ptypes.Inode, set[pathlib.Path]](set)
    dataflow_graph = DataflowGraph()
    parent_pid = dict[ptypes.Pid, ptypes.Pid]()

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

    def add_access(
            access: AccessMode,
            op_node: hb_graph.OpNode,
            inode: ptypes.Inode,
            version_num: int | None = None,
    ) -> None:
        if version_num is None:
            version_num = inode_to_version[inode]
        version = InodeVersionNode(inode, version_num, frozenset(inode_to_paths[inode]))
        next_version = InodeVersionNode(inode, version_num + 1, frozenset(inode_to_paths[inode]))
        ensure_state(op_node, PidState.READING if access == AccessMode.READ else PidState.WRITING)
        op_node = last_op_in_process[op_node.pid]
        match access:
            case AccessMode.WRITE:
                dataflow_graph.add_edge(op_node, next_version)
                dataflow_graph.add_edge(version, next_version)
            case AccessMode.TRUNCATE_WRITE:
                dataflow_graph.add_edge(op_node, next_version)
            case AccessMode.READ_WRITE:
                dataflow_graph.add_edge(version, op_node)
                dataflow_graph.add_edge(op_node, next_version)
            case AccessMode.READ:
                dataflow_graph.add_edge(version, op_node)
            case _:
                raise RuntimeError()

    def add_close(op_node: hb_graph.OpNode, fd: int) -> None:
        if file_desc := proc_fd_to_fd[node.pid].get(fd):
            file_desc = proc_fd_to_fd[node.pid][fd]
            file_desc.close_ops.append(node)
            del proc_fd_to_fd[op_node.pid][fd]
            if file_desc.access_mode != AccessMode.READ:
                # Reads are handled at the open
                # Everything else is handled at the close
                add_access(file_desc.access_mode, op_node, file_desc.inode, file_desc.version)
        else:
            pass
            # warnings.warn(f"Process {op_node.pid} successfully closed an FD {fd} we never traced. This could come from pipe or pipe2.")

    for node in tqdm.tqdm(
            networkx.topological_sort(reduced_hb_graph),
            total=len(reduced_hb_graph),
            desc="Finding DFG",
    ):
        op = probe_log.get_op(*node.op_quad())
        match op.data:
            case ops.InitExecEpochOp():
                add_node(node)
                exe_inode = ptypes.InodeVersion.from_probe_path(op.data.exe).inode
                add_access(AccessMode.READ, node, exe_inode)
                proc_fd_to_fd[node.pid][0] = FileDescriptor(
                    AccessMode.READ,
                    node,
                    [],
                    ptypes.InodeVersion.from_probe_path(op.data.stdin).inode,
                    True,
                    0,
                )
                proc_fd_to_fd[node.pid][1] = FileDescriptor(
                    AccessMode.WRITE,
                    node,
                    [],
                    ptypes.InodeVersion.from_probe_path(op.data.stdout).inode,
                    True,
                    0,
                )
                proc_fd_to_fd[node.pid][2] = FileDescriptor(
                    AccessMode.WRITE,
                    node,
                    [],
                    ptypes.InodeVersion.from_probe_path(op.data.stderr).inode,
                    True,
                    0,
                )
            case ops.OpenOp():
                # TODO: Verify that inode_version confirms the story told by inode_epochs
                inode = ptypes.InodeVersion.from_probe_path(op.data.path).inode
                if op.data.fd in proc_fd_to_fd[node.pid]:
                    add_close(node, op.data.fd)
                access_mode = AccessMode.from_open_flags(op.data.flags)
                version = inode_to_version[inode]
                inode_to_paths[inode].add(pathlib.Path(op.data.path.path.decode()))
                if access_mode == AccessMode.READ:
                    add_access(access_mode, node, inode, version)
                proc_fd_to_fd[node.pid][op.data.fd] = FileDescriptor(
                    access_mode,
                    node,
                    [],
                    inode,
                    bool(op.data.flags & os.O_CLOEXEC),
                    version,
                )
            case ops.ExecOp():
                for fd, file_desc in list(proc_fd_to_fd[node.pid].items()):
                    if file_desc.cloexec:
                        add_close(node, fd)
                exe_inode = ptypes.InodeVersion.from_probe_path(op.data.path).inode
                inode_to_paths[exe_inode].add(pathlib.Path(op.data.path.path.decode()))
            case ops.DupOp():
                if old_file_desc := proc_fd_to_fd[node.pid].get(op.data.old):
                    # dup2 and dup3 close the new FD, if it was open
                    if op.data.new in list(proc_fd_to_fd[node.pid]):
                        add_close(node, op.data.new)
                    proc_fd_to_fd[node.pid][op.data.new] = old_file_desc
                else:
                    pass
                    # warnings.warn(f"Process {node.pid} successfully closed an FD {op.data.old} we never traced. This could come from pipe or pipe2.")
            case ops.CloseOp():
                add_close(node, op.data.fd)
            case ops.CloneOp():
                if not (op.data.flags & os.CLONE_THREAD):
                    target = ptypes.Pid(op.data.task_id)
                    if op.data.flags & os.CLONE_FILES:
                        proc_fd_to_fd[target] = proc_fd_to_fd[node.pid]
                    else:
                        proc_fd_to_fd[target] = copy.deepcopy(proc_fd_to_fd[node.pid])
                    ensure_state(node, PidState.WRITING)
                    parent_pid[target] = node.pid
            case ops.SpawnOp():
                warnings.warn("Not implemented: track what the heck happens after a posix_spawn call")
                target = ptypes.Pid(op.data.child_pid)
                proc_fd_to_fd[target] = copy.deepcopy(proc_fd_to_fd[node.pid])
                ensure_state(node, PidState.WRITING)
                parent_pid[target] = node.pid

        is_last_op_in_process = not any(
            successor.pid == node.pid
            for successor in reduced_hb_graph.successors(node)
        )
        if is_last_op_in_process:
            for fd, file_desc in list(proc_fd_to_fd[node.pid].items()):
                add_close(node, fd)

    print("done hard part of constructing DFG")
    if check:
        print("checking")
        validate_dataflow_graph(probe_log, dataflow_graph)
    print("returning")

    return dataflow_graph


def combine_indistinguishable_inodes(
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
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
    print("computing quotient")
    quotient = networkx.quotient_graph(dataflow_graph, same_neighbors)
    for _, data in quotient.nodes(data=True):
        del data["nnodes"]
        del data["density"]
        del data["graph"]
        del data["nedges"]
    print("done with quotiont; relabeling")
    ret = graph_utils.map_nodes(node_mapper, quotient, False)
    print("done with relabeling")
    return ret


def validate_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: DataflowGraph,
        # dataflow_graph_tc: DataflowGraph | None,
) -> None:
    # if dataflow_graph_tc is None:
    #     dataflow_graph_tc = graph_utils.add_self_loops(networkx.transitive_closure(dataflow_graph), False)
    # TODO
    # if not networkx.is_directed_acyclic_graph(dataflow_graph):
    #     cycle = list(networkx.find_cycle(dataflow_graph))
    #     output = pathlib.Path("invalid.dot").resolve()
    #     label_nodes(probe_log, dataflow_graph)
    #     graph_utils.serialize_graph(dataflow_graph, output)
    #     raise ptypes.InvalidProbeLog(f"Found a cycle in graph: {cycle}; see {output}")

    if not networkx.is_weakly_connected(dataflow_graph):
        warnings.warn(f"Graph is not strongly connected: {'\n'.join(map(str, networkx.weakly_connected_components(dataflow_graph)))}")

    # inode_to_last_node: dict[ptypes.Inode, None | InodeVersionNode] = {
    #     node.inode: None
    #     for node in dataflow_graph.nodes()
    #     if isinstance(node, InodeVersionNode)
    # }
    # TODO
    # for node in networkx.topological_sort(dataflow_graph):
    #     if isinstance(node, InodeVersionNode):
    #         if last_node := inode_to_last_node.get(node.inode):
    #             if last_node.version + 1 == node.version:
    #                 if not any(
    #                         writer in dataflow_graph_tc.predecessors(node)
    #                         for writer in dataflow_graph.predecessors(last_node)
    #                 ):
    #                     pass
    #                     #raise ptypes.InvalidProbeLog(f"We incremented versions to {node.version}, but there is no path from {last_node} to {node}")
    #             else:
    #                 if last_node.version != node.version:
    #                     raise ptypes.InvalidProbeLog(f"We went from {last_node.version} to {node.version}")
    #         else:
    #             if node.version not in {0, 1}:
    #                 raise ptypes.InvalidProbeLog(f"Version of an initial access should be 0 or 1 not {node.version} ")
    #         inode_to_last_node[node.inode] = node
        # TODO: Check CloseOp and OpenOp
        # OpenOp.path should match CloseOp.path


def label_nodes(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: CompressedDataflowGraph,
        max_args: int = 5,
        max_arg_length: int = 80,
        max_path_segment_length: int = 20,
        max_paths_per_inode: int = 1,
        max_inodes_per_set: int = 5,
) -> None:
    count = dict[tuple[ptypes.Pid, ptypes.ExecNo], int]()
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
                        args = "\n".join(
                            textwrap.shorten(
                                arg.decode(errors="backslashreplace"),
                                width=max_arg_length,
                            )
                            for arg in op.data.argv[:max_args]
                        )
                        elipses = "\n..." if len(op.data.argv) > max_args else ""
                        data["label"] = f"exec\n{args}{elipses}\n{node.pid}"
                    else:
                        data["label"] = f"(child proc {node.pid})"
                else:
                    data["label"] = f"proc {node.pid} v{count[(node.pid, node.exec_no)]}"
                    count[(node.pid, node.exec_no)] += 1
                data["label"] += "\n" + type(op.data).__name__
                data["id"] = str(node)
            case frozenset():
                def shorten_path(input: pathlib.Path) -> str:
                    return ("/" if input.is_absolute() else "") + "/".join(
                        textwrap.shorten(part, width=max_path_segment_length)
                        for part in input.parts
                        if part != "/"
                    )
                inode_labels = []
                for inode in list(node)[:max_inodes_per_set]:
                    inode_label = []
                    inode_label.append(f"{inode.inode.number} v{inode.version}")
                    for path in sorted(inode.paths, key=lambda path: len(str(path)))[:max_paths_per_inode]:
                        inode_label.append(shorten_path(path))
                    inode_labels.append("\n".join(inode_label))
                data["label"] = "\n".join(inode_labels)
                data["shape"] = "rectangle"
                data["id"] = str(hash(node))

    for node0, node1, data in tqdm.tqdm(
            dataflow_graph.edges(data=True),
            desc="Labelling DFG edges",
    ):
        if isinstance(node0, hb_graph.OpNode) and isinstance(node1, hb_graph.OpNode) and node0.pid != node1.pid:
            data["style"] = "dashed"

    # dataflow_graph_tc = graph_utils.add_self_loops(networkx.transitive_closure(dataflow_graph), False)
    # inode_to_last_node: dict[ptypes.Inode, None | InodeVersionNode] = {
    #     node.inode: None
    #     for node in dataflow_graph.nodes()
    #     if isinstance(node, InodeVersionNode)
    # }
    # for node in networkx.topological_sort(dataflow_graph):
    #     if isinstance(node, InodeVersionNode):
    #         if last_node := inode_to_last_node.get(node.inode):
    #             if last_node.version + 1 == node.version:
    #                 if not any(
    #                         writer in dataflow_graph_tc.predecessors(node)
    #                         for writer in dataflow_graph.predecessors(last_node)
    #                 ):
    #                     raise ptypes.InvalidProbeLog(f"We incremented versions to {node.version}, but there is no path from {last_node} to {node}")
    # TODO
