import collections
import dataclasses
import enum
import os
import pathlib
import rich
import sys
import typing
import networkx
import numpy
from .ptypes import TaskType, Pid, ExecNo, Tid, ProbeLog, Inode, InodeVersion, Host, Device
from .ops import Op, CloneOp, ExecOp, WaitOp, OpenOp
from .hb_graph import OpNode, HbGraph


class EdgeLabel(enum.IntEnum):
    PROGRAM_ORDER = 1
    FORK_JOIN = 2
    EXEC = 3
 
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

# type for the edges
EdgeType: typing.TypeAlias = tuple[OpNode, OpNode]


if typing.TYPE_CHECKING:
    DfGraph: typing.TypeAlias = networkx.DiGraph[FileAccess | ProcessNode]
    ProcessTree: typing.TypeAlias = networkx.DiGraph[str]
else:
    DfGraph = networkx.DiGraph
    ProcessTree = networkx.DiGraph

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


def get_op(probe_log: ProbeLog, pid: Pid, eno: ExecNo, tid: Tid, op_no: int) -> Op:
    return probe_log.processes[pid].execs[eno].threads[tid].ops[op_no]


def probe_log_to_process_tree(probe_log: ProbeLog) -> ProcessTree:
    G = ProcessTree()

    def epoch_node_id(pid: int, epoch_no: int) -> str:
        return f"pid{pid}_epoch{epoch_no}"

    for pid, process in probe_log.processes.items():
        for epoch_no, epoch in process.execs.items():
            cmd_args = None

            for tid, thread in epoch.threads.items():
                for op in thread.ops:
                    op_data = op.data

                    if isinstance(op_data, ExecOp):
                        args_list = [arg.decode('utf-8') for arg in op_data.argv]
                        cmd_args = " ".join(args_list)
                        break
                if cmd_args:
                    break

            if cmd_args:
                label = f"PID={pid}\n {cmd_args}"
            else:
                label = f"PID={pid}\n cloned from parent"

            node_id = epoch_node_id(pid, epoch_no)
            G.add_node(node_id, label=label)

    for pid, process in probe_log.processes.items():
        for exec_epoch_no, exec_epoch in process.execs.items():
            parent_node_id = epoch_node_id(pid, exec_epoch_no)

            for tid, thread in exec_epoch.threads.items():
                for op in thread.ops:
                    op_data = op.data

                    if isinstance(op_data, CloneOp) and op_data.ferrno == 0:
                        child_pid = op_data.task_id
                        if child_pid in probe_log.processes:
                            child_epoch = 0
                            child_node_id = epoch_node_id(child_pid, child_epoch)

                            if G.has_node(child_node_id):
                                G.add_edge(parent_node_id, child_node_id, label="clone", constraint="true")

                    if isinstance(op_data, ExecOp):
                        new_epoch_no = exec_epoch_no + 1
                        new_node_id = epoch_node_id(pid, new_epoch_no)

                        if G.has_node(new_node_id):
                            G.add_edge(parent_node_id, new_node_id, label="exec", constraint="false")

    return G

def get_max_parallelism_latest(hb_graph: HbGraph, probe_log: ProbeLog) -> int:
    visited = set()
    # counter is set to 1 to include the main parent process
    counter = 1 
    max_counter = 1
    start_node = [node for node in hb_graph.nodes() if hb_graph.in_degree(node) == 0][0]
    queue = collections.deque[tuple[OpNode, OpNode | None]]([(start_node, None)])  # (current_node, parent_node)
    while queue:
        node, parent = queue.popleft()
        if node in visited:
            continue
        pid, exec_epoch_no, tid, op_index = node.op_quad()
        if(parent):
            parent_pid, parent_exec_epoch_no, parent_tid, parent_op_index = parent.op_quad()
            parent_op = get_op(probe_log, parent_pid, parent_exec_epoch_no, parent_tid, parent_op_index).data
        node_op = get_op(probe_log, pid, exec_epoch_no, tid, op_index).data

        visited.add(node)

        # waitOp can be reached from the cloneOp and the last op of the child process
        # is waitOp is reached via the cloneOp we ignore the node
        if isinstance(node_op, WaitOp):
            if parent and isinstance(parent_op, CloneOp):
                visited.remove(node)
                continue
        # for every clone the new process runs in parallel with other so we increment the counter
        if isinstance(node_op, CloneOp):
            counter += 1
            max_counter = max(counter, max_counter)
        # for every waitOp the control comes back to the parent process so we decrement the counter
        elif isinstance(node_op, WaitOp):
            if node_op.task_id!=0:
                counter -= 1
        
        # Add neighbors to the queue
        for neighbor in hb_graph.successors(node):
            queue.append((neighbor, node))

    return max_counter
