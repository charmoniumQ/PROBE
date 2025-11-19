# From 2a63c07eaa53a0e017eb0ad557ebbfffcaf66fc8
# Following #138

###
# New

import dataclasses
import collections
import pathlib
import typing
import os

import networkx
import rich.console


#####
# analysis.py:23

@dataclasses.dataclass(frozen=True)
class ProcessNode:
    pid: int
    cmd: tuple[str,...]


@dataclasses.dataclass(frozen=True)
class FileAccess:
    inode_version: InodeVersion
    path: pathlib.Path

    @property
    def label(self) -> str:
        return f"{self.path!s} inode {self.inode_version.inode}"

#####
# New

Pid = int
ExecNo = int
Tid = int
OpNode = tuple[Pid, ExecNo, Tid, int]
HbGraph = networkx.DiGraph[OpNode]
DfGraph = networkx.DiGraph[FileAccess | ProcessNode]
class ProbeLog:
    pass

#####
# analysis.py:47


def traverse_hb_for_dfgraph(probe_log: ProbeLog, starting_node: OpNode, traversed: set[int] , dataflow_graph: DfGraph, cmd_map: dict[int, list[str]], inode_version_map: dict[int, set[InodeVersion]], hb_graph: HbGraph) -> None:
    starting_pid = starting_node.pid

    starting_op = get_op(probe_log, *starting_node.op_quad())

    name_map = collections.defaultdict[Inode, list[pathlib.Path]](list)

    target_nodes = collections.defaultdict[int, list[OpNode]](list)
    console = rich.console.Console(file=sys.stderr)

    print("starting at", starting_node, starting_op)

    for edge in networkx.bfs_edges(hb_graph, starting_node):

        pid, exec_epoch_no, tid, op_index = edge[0].op_quad()

        # check if the process is already visited when waitOp occurred
        if pid in traversed or tid in traversed:
            continue

        op = get_op(probe_log, pid, exec_epoch_no, tid, op_index).data
        next_op = get_op(probe_log, *edge[1].op_quad()).data
        if isinstance(op, OpenOp):
            access_mode = op.flags & os.O_ACCMODE
            processNode = ProcessNode(pid=pid, cmd=tuple(cmd_map[pid]))
            dataflow_graph.add_node(processNode, label=processNode.cmd)
            inode = Inode(Host.localhost(), Device(op.path.device_major, op.path.device_minor), op.path.inode)
            path_str = op.path.path.decode("utf-8")
            curr_version = InodeVersion(inode, numpy.datetime64(op.path.mtime.sec * int(1e9) + op.path.mtime.nsec, "ns"), op.path.size)
            inode_version_map.setdefault(op.path.inode, set())
            inode_version_map[op.path.inode].add(curr_version)
            fileNode = FileAccess(curr_version, pathlib.Path(path_str))
            dataflow_graph.add_node(fileNode)
            path = pathlib.Path(op.path.path.decode("utf-8"))
            if path not in name_map[inode]:
                name_map[inode].append(path)
            if access_mode == os.O_RDONLY:
                dataflow_graph.add_edge(fileNode, processNode)
            elif access_mode == os.O_WRONLY:
                dataflow_graph.add_edge(processNode, fileNode)
            elif access_mode == 2:
                console.print(f"Found file {path_str} with access mode O_RDWR", style="red")
            else:
                raise Exception("unknown access mode")
        elif isinstance(op, CloneOp):
            if op.task_type == TaskType.TASK_PID:
                if edge[0].pid != edge[1].pid:
                    target_nodes[op.task_id].append(edge[1])
                    continue
            elif op.task_type == TaskType.TASK_PTHREAD:
                if edge[0].tid != edge[1].tid:
                    target_nodes[op.task_id].append(edge[1])
                    continue
            if op.task_type != TaskType.TASK_PTHREAD and op.task_type != TaskType.TASK_ISO_C_THREAD:

                processNode1 = ProcessNode(pid = pid, cmd=tuple(cmd_map[pid]))
                processNode2 = ProcessNode(pid = op.task_id, cmd=tuple(cmd_map[op.task_id]))
                dataflow_graph.add_node(processNode1, label = " ".join(arg for arg in processNode1.cmd))
                dataflow_graph.add_node(processNode2, label = " ".join(arg for arg in processNode2.cmd))
                dataflow_graph.add_edge(processNode1, processNode2)
            target_nodes[op.task_id] = list()
        elif isinstance(op, WaitOp) and op.options == 0:
            for node in target_nodes[op.task_id]:
                traverse_hb_for_dfgraph(probe_log, node, traversed, dataflow_graph, cmd_map, inode_version_map, hb_graph)
                traversed.add(node.tid)
        # return back to the WaitOp of the parent process
        if isinstance(next_op, WaitOp):
            if next_op.task_id == starting_pid or next_op.task_id == starting_op.pthread_id:
                return


def probe_log_to_dataflow_graph(probe_log: ProbeLog, hb_graph: HbGraph) -> DfGraph:
    dataflow_graph = DfGraph()
    root_node = [n for n in hb_graph.nodes() if hb_graph.out_degree(n) > 0 and hb_graph.in_degree(n) == 0][0]
    traversed: set[int] = set()
    cmd_map = collections.defaultdict[int, list[str]](list)
    for edge in list(hb_graph.edges())[::-1]:
        pid, exec_epoch_no, tid, op_index = edge[0].op_quad()
        op = get_op(probe_log, pid, exec_epoch_no, tid, op_index).data
        if isinstance(op, ExecOp):
            if pid.main_thread() == tid and exec_epoch_no == 0:
                cmd_map[tid] = [arg.decode(errors="surrogate") for arg in op.argv]

    inode_version_map: dict[int, set[InodeVersion]] = {}
    traverse_hb_for_dfgraph(probe_log, root_node, traversed, dataflow_graph, cmd_map, inode_version_map, hb_graph)

    file_version: dict[str, int] = {}
    for inode, versions in inode_version_map.items():
        sorted_versions = sorted(
            versions,
            key=lambda version: typing.cast(int, version.mtime),
        )
        for idx, version in enumerate(sorted_versions):
            str_id = f"{inode}_{version.mtime}"
            file_version[str_id] = idx

    for idx, node in enumerate(dataflow_graph.nodes()):
        if isinstance(node, FileAccess):
            str_id = f"{inode}_{version.mtime}"
            label = f"{node.path} inode {node.inode_version.inode.number} fv {file_version[str_id]} "
            networkx.set_node_attributes(dataflow_graph, {node: label}, "label") # type: ignore

    return dataflow_graph
