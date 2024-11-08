import typing
import networkx as nx  # type: ignore
from .types import Inode, ProbeLog, TaskType, Host, Pid, ExecNo, Tid
from .ops import Op, CloneOp, ExecOp, WaitOp, OpenOp, CloseOp, InitProcessOp, InitExecEpochOp, InitThreadOp, StatOp
from enum import IntEnum
import rich
import sys
from dataclasses import dataclass
import pathlib
import os
import collections


class EdgeLabels(IntEnum):
    PROGRAM_ORDER = 1
    FORK_JOIN = 2
    EXEC = 3
 
@dataclass(frozen=True)
class ProcessNode:
    pid: int
    cmd: tuple[str,...]


@dataclass(frozen=True)
class FileNode:
    inode: Inode
    version: int
    file: str

    @property
    def label(self) -> str:
        return f"{self.file} v{self.version}"

# type alias for a node
Node = tuple[Pid, ExecNo, Tid, int]

# type for the edges
EdgeType = tuple[Node, Node]



# TODO: Rename "digraph" to "hb_graph" in the entire project.
# Digraph (aka "directed graph") is too vague a term; the proper name is "happens-before graph".
# Later on, we will have a function that transforms an hb graph to file graph (both of which are digraphs)
def probe_log_to_digraph(process_tree_prov_log: ProbeLog) -> nx.DiGraph:
    # [pid, exec_epoch_no, tid, op_index]
    program_order_edges = list[tuple[Node, Node]]()
    fork_join_edges = list[tuple[Node, Node]]()
    exec_edges = list[tuple[Node, Node]]()
    nodes = list[Node]()
    proc_to_ops = dict[tuple[int, int, int], list[Node]]()
    last_exec_epoch = dict[int, int]()
    for pid, process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.execs.items():
            # to find the last executing epoch of the process
            last_exec_epoch[pid] = max(last_exec_epoch.get(pid, 0), exec_epoch_no)
            # Reduce each thread to the ops we actually care about
            for tid, thread in exec_epoch.threads.items():
                context = (pid, exec_epoch_no, tid)
                ops = list[Node]()
                # Filter just the ops we are interested in
                op_index = 0
                for op_index, op in enumerate(thread.ops):
                    ops.append((*context, op_index))
                # Add just those ops to the graph
                nodes.extend(ops)
                program_order_edges.extend(zip(ops[:-1], ops[1:])) 
                # Store these so we can hook up forks/joins between threads
                proc_to_ops[context] = ops

    # Define helper functions
    def first(pid: int, exid: int, tid: int) -> Node:
        return proc_to_ops[(pid, exid, tid)][0]

    def last(pid: int, exid: int, tid: int) -> Node:
        return proc_to_ops[(pid, exid, tid)][-1]

    def get_first_pthread(pid: int, exid: int, target_pthread_id: int) -> list[Node]:
        ret = list[Node]()
        for pid, process in process_tree_prov_log.processes.items():
            for exid, exec_epoch in process.execs.items():
                for tid, thread in exec_epoch.threads.items():
                    for op_index, op in enumerate(thread.ops):
                        if op.pthread_id == target_pthread_id:
                            ret.append((pid, exid, tid, op_index))
                        break
        return ret

    def get_last_pthread(pid: int, exid: int, target_pthread_id: int) -> list[Node]:
        ret = list[Node]()
        for pid, process in process_tree_prov_log.processes.items():
            for exid, exec_epoch in process.execs.items():
                for tid, thread in exec_epoch.threads.items():
                    for op_index, op in list(enumerate(thread.ops))[::-1]:
                        if op.pthread_id == target_pthread_id:
                            ret.append((pid, exid, tid, op_index))
                        break
        return ret

    # Hook up forks/joins
    for node in list(nodes):
        pid, exid, tid, op_index = node
        op_data = process_tree_prov_log.processes[pid].execs[exid].threads[tid].ops[op_index].data
        target: tuple[int, int, int]
        if False:
            pass
        elif isinstance(op_data, CloneOp) and op_data.ferrno == 0:
            if False:
                pass
            elif op_data.task_type == TaskType.TASK_PID:
                # Spawning a thread links to the current PID and exec epoch
                target = (op_data.task_id, 0, op_data.task_id)
                fork_join_edges.append((node, first(*target)))
            elif op_data.task_type == TaskType.TASK_TID:
                target = (pid, exid, op_data.task_id)
                fork_join_edges.append((node, first(*target)))
            elif op_data.task_type == TaskType.TASK_PTHREAD:
                for dest in get_first_pthread(pid, exid, op_data.task_id):
                    fork_join_edges.append((node, dest))
            else:
                raise RuntimeError(f"Task type {op_data.task_type} supported")
        elif isinstance(op_data, WaitOp) and op_data.ferrno == 0 and op_data.task_id > 0:
            if False:
                pass
            elif op_data.task_type == TaskType.TASK_PID:
                target = (op_data.task_id, last_exec_epoch.get(op_data.task_id, 0), op_data.task_id)
                fork_join_edges.append((last(*target), node))
            elif op_data.task_type == TaskType.TASK_TID:
                target = (pid, exid, op_data.task_id)
                fork_join_edges.append((last(*target), node))
            elif op_data.ferrno == 0 and op_data.task_type == TaskType.TASK_PTHREAD:
                for dest in get_last_pthread(pid, exid, op_data.task_id):
                    fork_join_edges.append((dest, node))
        elif isinstance(op_data, ExecOp):
            # Exec brings same pid, incremented exid, and main thread
            target = pid, exid + 1, pid
            exec_edges.append((node, first(*target)))

    process_graph = nx.DiGraph()
    for node in nodes:
        process_graph.add_node(node)

    def add_edges(edges:list[tuple[Node, Node]], label:EdgeLabels) -> None:
        for node0, node1 in edges:
            process_graph.add_edge(node0, node1, label=label)
    
    add_edges(program_order_edges, EdgeLabels.PROGRAM_ORDER)
    add_edges(exec_edges, EdgeLabels.EXEC)
    add_edges(fork_join_edges, EdgeLabels.FORK_JOIN)
    return process_graph

def traverse_hb_for_dfgraph(
        process_tree_prov_log: ProbeLog,
        starting_node: Node,
        traversed: set[int],
        dataflow_graph:nx.DiGraph,
        file_version_map: dict[Inode, int],
        shared_files: set[Inode],
        cmd_map: dict[int, list[str]],
) -> None:
    starting_pid = starting_node[0]
    
    starting_op = prov_log_get_node(process_tree_prov_log, starting_node[0], starting_node[1], starting_node[2], starting_node[3])
    process_graph = probe_log_to_digraph(process_tree_prov_log)
    
    edges = list_edges_from_start_node(process_graph, starting_node)
    name_map = collections.defaultdict[Inode, list[pathlib.Path]](list)

    target_nodes = collections.defaultdict[int, list[Node]](list)
    console = rich.console.Console(file=sys.stderr)
    
    for edge in edges:  
        pid, exec_epoch_no, tid, op_index = edge[0]
        
        # check if the process is already visited when waitOp occurred
        if pid in traversed or tid in traversed:
            continue
        
        op = prov_log_get_node(process_tree_prov_log, pid, exec_epoch_no, tid, op_index).data
        next_op = prov_log_get_node(process_tree_prov_log, edge[1][0], edge[1][1], edge[1][2], edge[1][3]).data
        # when we move to a new process which is not a child process but an independent process we empty the shared_files 
        if edge[0][0]!=edge[1][0] and not isinstance(op, CloneOp) and not isinstance(next_op, WaitOp) and edge[1][1] == 0 and edge[1][3] == 0:
            shared_files = set()
        if isinstance(op, OpenOp):
            access_mode = op.flags & os.O_ACCMODE
            processNode = ProcessNode(pid=pid, cmd=tuple(cmd_map[pid]))
            dataflow_graph.add_node(processNode, label=processNode.cmd)
            file = Inode(Host.localhost(), op.path.device_major, op.path.device_minor, op.path.inode)
            path_str = op.path.path.decode("utf-8")
            if access_mode == os.O_RDONLY:
                curr_version = file_version_map[file]
                fileNode = FileNode(file, curr_version, path_str)
                dataflow_graph.add_node(fileNode, label = fileNode.label)
                path = pathlib.Path(op.path.path.decode("utf-8"))
                if path not in name_map[file]:
                    name_map[file].append(path)
                dataflow_graph.add_edge(fileNode, processNode)
            elif access_mode == os.O_WRONLY:
                curr_version = file_version_map[file]
                if file in shared_files:
                    fileNode2 = FileNode(file, curr_version, path_str)
                    dataflow_graph.add_node(fileNode2, label = fileNode2.label)
                else:
                    file_version_map[file] = curr_version + 1
                    fileNode2 = FileNode(file, curr_version+1, path_str)
                    dataflow_graph.add_node(fileNode2, label = fileNode2.label)
                    if starting_pid == pid:
                        # shared_files: shared_files helps us keep track of the files shared between parent and child processes. This ensures that when the children write to the file, the version of the file is not incremented multiple times
                        shared_files.add(file)
                path = pathlib.Path(op.path.path.decode("utf-8"))
                if path not in name_map[file]:
                    name_map[file].append(path)          
                dataflow_graph.add_edge(processNode, fileNode2)
            elif access_mode == 2:
                console.print(f"Found file {path_str} with access mode O_RDWR", style="red")
            else:
                raise Exception("unknown access mode")
        elif isinstance(op, CloneOp):
            if op.task_type == TaskType.TASK_PID:
                if edge[0][0] != edge[1][0]:
                    target_nodes[op.task_id].append(edge[1])
                    continue
            elif op.task_type == TaskType.TASK_PTHREAD:
                if edge[0][2] != edge[1][2]:
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
                traverse_hb_for_dfgraph(process_tree_prov_log, node, traversed, dataflow_graph, file_version_map, shared_files, cmd_map)
                traversed.add(node[2])
        # return back to the WaitOp of the parent process
        if isinstance(next_op, WaitOp):
            if next_op.task_id == starting_pid or next_op.task_id == starting_op.pthread_id:
                return

def list_edges_from_start_node(graph: nx.DiGraph, start_node: Node) -> list[EdgeType]:
    all_edges = list(graph.edges())
    start_index = next(i for i, edge in enumerate(all_edges) if edge[0] == start_node)
    ordered_edges = all_edges[start_index:] + all_edges[:start_index] 
    return ordered_edges

def probe_log_to_dataflow_graph(process_tree_prov_log: ProbeLog) -> nx.DiGraph:
    dataflow_graph = nx.DiGraph()
    file_version_map = collections.defaultdict[Inode, int](lambda: 0)
    process_graph = probe_log_to_digraph(process_tree_prov_log)
    root_node = [n for n in process_graph.nodes() if process_graph.out_degree(n) > 0 and process_graph.in_degree(n) == 0][0]
    traversed: set[int] = set()
    cmd_map = collections.defaultdict[int, list[str]](list)
    for edge in list(nx.edges(process_graph))[::-1]:
        pid, exec_epoch_no, tid, op_index = edge[0]
        op = prov_log_get_node(process_tree_prov_log, pid, exec_epoch_no, tid, op_index).data
        if isinstance(op, ExecOp):
            if pid == tid and exec_epoch_no == 0:
                cmd_map[tid] = [arg.decode(errors="surrogate") for arg in op.argv]
    shared_files:set[Inode] = set()
    traverse_hb_for_dfgraph(process_tree_prov_log, root_node, traversed, dataflow_graph, file_version_map, shared_files, cmd_map)
    return dataflow_graph

def prov_log_get_node(prov_log: ProbeLog, pid: Pid, eno: ExecNo, tid: Tid, op_no: int) -> Op:
    return prov_log.processes[pid].execs[eno].threads[tid].ops[op_no]


def validate_hb_closes(probe_log: ProbeLog, process_graph: nx.DiGraph) -> list[str]:
    # Note that this test doesn't work if a process "intentionally" leaves a fd open for its child.
    # E.g., bash-in-pipe
    probe_log_reverse = process_graph.reverse()
    ret = list[str]()
    reserved_fds = {0, 1, 2}
    for node in process_graph.nodes:
        op = prov_log_get_node(probe_log, *node)
        if isinstance(op.data, CloseOp) and op.data.ferrno == 0:
            for closed_fd in range(op.data.low_fd, op.data.high_fd + 1):
                if closed_fd not in reserved_fds:
                    for pred_node in nx.dfs_preorder_nodes(probe_log_reverse, node):
                        pred_op = prov_log_get_node(probe_log, *pred_node)
                        if isinstance(pred_op.data, OpenOp) and pred_op.data.fd == closed_fd and op.data.ferrno == 0:
                            break
                    else:
                        ret.append(f"Close of {closed_fd} in {node} is not preceeded by corresponding open")
    return ret


def validate_hb_waits(probe_log: ProbeLog, process_graph: nx.DiGraph) -> list[str]:
    probe_log_reverse = process_graph.reverse()
    ret = list[str]()
    for node in process_graph.nodes:
        op = prov_log_get_node(probe_log, *node)
        if isinstance(op.data, WaitOp) and op.data.ferrno == 0:
            for pred_node in nx.dfs_preorder_nodes(probe_log_reverse, node):
                pred_op = prov_log_get_node(probe_log, *pred_node)
                pid1, eid1, tid1, opid1 = pred_node
                if isinstance(pred_op.data, CloneOp) and pred_op.data.task_type == op.data.task_type and pred_op.data.task_id == op.data.task_id and op.data.ferrno == 0:
                    break
            else:
                ret.append(f"Wait of {op.data.task_id} in {node} is not preceeded by corresponding clone")
    return ret

def validate_hb_clones(probe_log: ProbeLog, process_graph: nx.DiGraph) -> list[str]:
    ret = list[str]()
    for node in process_graph.nodes:
        op = prov_log_get_node(probe_log, *node)
        if isinstance(op.data, CloneOp) and op.data.ferrno == 0:
            for node1 in process_graph.successors(node):
                pid1, exid1, tid1, op_no1 = node1
                op1 = prov_log_get_node(probe_log, *node1)
                if False:
                    pass
                elif op.data.task_type == TaskType.TASK_PID:
                    if isinstance(op1.data, InitProcessOp):
                        if op.data.task_id != pid1:
                            ret.append(f"CloneOp {node} returns {op.data.task_id} but the next op has pid {pid1}")
                        break
                elif op.data.task_type == TaskType.TASK_TID:
                    if isinstance(op1.data, InitThreadOp):
                        if op.data.task_id != tid1:
                            ret.append(f"CloneOp {node} returns {op.data.task_id} but the next op has tid {tid1}")
                        break
                elif op.data.task_type == TaskType.TASK_PTHREAD and op.data.task_id == op1.pthread_id:
                    break
                elif op.data.task_type == TaskType.TASK_ISO_C_THREAD and op.data.task_id == op1.iso_c_thread_id:
                    break
            else:
                ret.append(f"Could not find a successor for CloneOp {node} {TaskType(op.data.task_type).name} in the target thread/process/whatever")
    return ret


def validate_hb_degree(probe_log: ProbeLog, process_graph: nx.DiGraph) -> list[str]:
    ret = list[str]()
    found_entry = False
    found_exit = False
    for node in process_graph.nodes:
        if process_graph.in_degree(node) == 0:
            if not found_entry:
                found_entry = True
            else:
                ret.append(f"Node {node} has no predecessors")
        if process_graph.out_degree(node) == 0:
            if not found_exit:
                found_exit = True
            else:
                ret.append(f"Node {node} has no successors")
    if not found_entry:
        ret.append("Found no entry node")
    if not found_exit:
        ret.append("Found no exit node")
    return ret


def validate_hb_acyclic(probe_log: ProbeLog, process_graph: nx.DiGraph) -> list[str]:
    try:
        cycle = nx.find_cycle(process_graph)
    except nx.NetworkXNoCycle:
        return []
    else:
        return [f"Cycle detected: {cycle}"]


def validate_hb_execs(probe_log: ProbeLog, process_graph: nx.DiGraph) -> list[str]:
    ret = list[str]()
    for node0 in process_graph.nodes():
        pid0, eid0, tid0, op0 = node0
        op0 = prov_log_get_node(probe_log, *node0)
        if isinstance(op0.data, ExecOp):
            for node1 in process_graph.successors(node0):
                pid1, eid1, tid1, op1 = node1
                op1 = prov_log_get_node(probe_log, *node1)
                if isinstance(op1.data, InitExecEpochOp):
                    if eid0 + 1 != eid1:
                        ret.append(f"ExecOp {node0} is followed by {node1}, whose exec epoch id should be {eid0 + 1}")
                    break
            else:
                ret.append(f"ExecOp {node0} is not followed by an InitExecEpochOp, but by {op1}.")
    return ret


def validate_hb_graph(processes: ProbeLog, hb_graph: nx.DiGraph) -> list[str]:
    ret = list[str]()
    # ret.extend(validate_hb_closes(processes, hb_graph))
    ret.extend(validate_hb_waits(processes, hb_graph))
    ret.extend(validate_hb_clones(processes, hb_graph))
    ret.extend(validate_hb_degree(processes, hb_graph))
    ret.extend(validate_hb_acyclic(processes, hb_graph))
    ret.extend(validate_hb_execs(processes, hb_graph))
    return ret


def relax_node(graph: nx.DiGraph, node: typing.Any) -> list[tuple[typing.Any, typing.Any]]:
    """Remove node from graph and attach its predecessors to its successors"""
    ret = list[tuple[typing.Any, typing.Any]]()
    for predecessor in graph.predecessors:
        for successor in graph.successors:
            ret.append((predecessor, successor))
            graph.add_edge(predecessor, successor)
    graph.remove_node(node)
    return ret

def color_hb_graph(prov_log: ProbeLog, process_graph: nx.DiGraph) -> None:
    label_color_map = {
        EdgeLabels.EXEC: 'yellow',
        EdgeLabels.FORK_JOIN: 'red',
        EdgeLabels.PROGRAM_ORDER: 'green',
    }

    for node0, node1, attrs in process_graph.edges(data=True):
        label: EdgeLabels = attrs['label']
        process_graph[node0][node1]['color'] = label_color_map[label]
        del attrs['label']

    for node, data in process_graph.nodes(data=True):
        pid, exid, tid, op_no = node
        op = prov_log_get_node(prov_log, *node)
        typ = type(op.data).__name__
        data["label"] = f"{pid}.{exid}.{tid}.{op_no}\n{typ}"
        if False:
            pass
        elif isinstance(op.data, OpenOp):
            data["label"] += f"\n{op.data.path.path.decode()} (fd={op.data.fd})"
        elif isinstance(op.data, CloseOp):
            fds = list(range(op.data.low_fd, op.data.high_fd + 1))
            data["label"] += "\n" + " ".join(map(str, fds))
        elif isinstance(op.data, CloneOp):
            data["label"] += f"\n{TaskType(op.data.task_type).name} {op.data.task_id}"
        elif isinstance(op.data, WaitOp):
            data["label"] += f"\n{TaskType(op.data.task_type).name} {op.data.task_id}"
        elif isinstance(op.data, StatOp):
            data["label"] += f"\n{op.data.path.path.decode()}"
