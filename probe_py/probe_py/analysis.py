import typing
import networkx as nx  # type: ignore
from .ptypes import TaskType, ProvLog
from .ops import Op, CloneOp, ExecOp, WaitOp, OpenOp, CloseOp, InitProcessOp, InitExecEpochOp, InitThreadOp, StatOp
from .graph_utils import list_edges_from_start_node
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
class InodeOnDevice:
    device_major: int
    device_minor: int
    inode: int

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InodeOnDevice):
            return NotImplemented
        return (self.device_major == other.device_major and
                self.device_minor == other.device_minor and
                self.inode == other.inode)
    def __hash__(self) -> int:
        return hash((self.device_major, self.device_minor, self.inode))

@dataclass(frozen=True)
class FileVersion:
    mtime_sec: int
    mtime_nsec: int

@dataclass(frozen=True)
class FileNode:
    inodeOnDevice: InodeOnDevice
    version: FileVersion
    file: str

    @property
    def label(self) -> str:
        return f"{self.file} inode {self.inodeOnDevice.inode}"

# type alias for a node
Node: typing.TypeAlias = tuple[int, int, int, int]

# type for the edges
EdgeType: typing.TypeAlias = tuple[Node, Node]

def validate_provlog(
        provlog: ProvLog,
) -> list[str]:
    ret = list[str]()
    waited_processes = set[tuple[TaskType, int]]()
    cloned_processes = set[tuple[TaskType, int]]()
    opened_fds = set[int]()
    closed_fds = set[int]()
    n_roots = 0
    for pid, process in provlog.processes.items():
        epochs = set[int]()
        first_op = process.exec_epochs[0].threads[pid].ops[0]
        if not isinstance(first_op.data, InitProcessOp):
            ret.append("First op in exec_epoch 0 should be InitProcessOp")
        else:
            if first_op.data.is_root:
                n_roots += 1
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            epochs.add(exec_epoch_no)
            first_ee_op_idx = 1 if exec_epoch_no == 0 else 0
            first_ee_op = exec_epoch.threads[pid].ops[first_ee_op_idx]
            if not isinstance(first_ee_op.data, InitExecEpochOp):
                ret.append(f"{first_ee_op_idx} in exec_epoch should be InitExecEpochOp")
            pthread_ids = {
                op.pthread_id
                for tid, thread in exec_epoch.threads.items()
                for op in thread.ops
            }
            iso_c_thread_ids = {
                op.pthread_id
                for tid, thread in exec_epoch.threads.items()
                for op in thread.ops
            }
            for tid, thread in exec_epoch.threads.items():
                first_thread_op_idx = first_ee_op_idx + (1 if tid == pid else 0)
                first_thread_op = thread.ops[first_thread_op_idx]
                if not isinstance(first_thread_op.data, InitThreadOp):
                    ret.append(f"{first_thread_op_idx} in exec_epoch should be InitThreadOp")
                for op in thread.ops:
                    if isinstance(op.data, WaitOp) and op.data.ferrno == 0:
                        # TODO: Replace TaskType(x) with x in this file, once Rust can emit enums
                        waited_processes.add((TaskType(op.data.task_type), op.data.task_id))
                    elif isinstance(op.data, CloneOp) and op.data.ferrno == 0:
                        cloned_processes.add((TaskType(op.data.task_type), op.data.task_id))
                        if op.data.task_type == TaskType.TASK_PID:
                            # New process implicitly also creates a new thread
                            cloned_processes.add((TaskType.TASK_TID, op.data.task_id))
                    elif isinstance(op.data, OpenOp) and op.data.ferrno == 0:
                        opened_fds.add(op.data.fd)
                    elif isinstance(op.data, ExecOp):
                        if len(op.data.argv) != op.data.argc:
                            ret.append("argv vs argc mismatch")
                        if len(op.data.env) != op.data.envc:
                            ret.append("env vs envc mismatch")
                        if not op.data.argv:
                            ret.append("No arguments stored in exec syscall")
                    elif isinstance(op.data, CloseOp) and op.data.ferrno == 0:
                        # Range in Python is up-to-not-including high_fd, so we add one to it.
                        closed_fds.update(range(op.data.low_fd, op.data.high_fd + 1))
                    elif isinstance(op.data, CloneOp) and op.data.ferrno == 0:
                        if False:
                            pass
                        elif op.data.task_type == TaskType.TASK_PID and op.data.task_id not in provlog.processes.keys():
                            ret.append(f"CloneOp returned a PID {op.data.task_id} that we didn't track")
                        elif op.data.task_type == TaskType.TASK_TID and op.data.task_id not in exec_epoch.threads.keys():
                            ret.append(f"CloneOp returned a TID {op.data.task_id} that we didn't track")
                        elif op.data.task_type == TaskType.TASK_PTHREAD and op.data.task_id not in pthread_ids:
                            ret.append(f"CloneOp returned a pthread ID {op.data.task_id} that we didn't track")
                        elif op.data.task_type == TaskType.TASK_ISO_C_THREAD and op.data.task_id not in iso_c_thread_ids:
                            ret.append(f"CloneOp returned a ISO C Thread ID {op.data.task_id} that we didn't track")
                    elif isinstance(op.data, InitProcessOp):
                        if exec_epoch_no != 0:
                            ret.append(f"InitProcessOp happened, but exec_epoch was not zero, was {exec_epoch_no}")
        expected_epochs = set(range(0, max(epochs) + 1))
        if expected_epochs - epochs:
            ret.append(f"Missing epochs for pid={pid}: {sorted(epochs - expected_epochs)}")
    reserved_fds = {0, 1, 2}
    if closed_fds - opened_fds - reserved_fds:
        # TODO: Problem due to some programs opening /dev/pts/0 in a way that libprobe doesn't notice, but they close it in a way we do notice.
        pass
        #ret.append(f"Closed more fds than we opened: {closed_fds=} {reserved_fds=} {opened_fds=}")
    elif waited_processes - cloned_processes:
        ret.append(f"Waited on more processes than we cloned: {waited_processes=} {cloned_processes=}")
    if n_roots != 1:
        ret.append(f"Got {n_roots} prov roots")
    return ret


# TODO: Rename "digraph" to "hb_graph" in the entire project.
# Digraph (aka "directed graph") is too vague a term; the proper name is "happens-before graph".
# Later on, we will have a function that transforms an hb graph to file graph (both of which are digraphs)
def provlog_to_digraph(process_tree_prov_log: ProvLog) -> nx.DiGraph:
    # [pid, exec_epoch_no, tid, op_index]
    program_order_edges = list[tuple[Node, Node]]()
    fork_join_edges = list[tuple[Node, Node]]()
    exec_edges = list[tuple[Node, Node]]()
    nodes = list[Node]()
    proc_to_ops = dict[tuple[int, int, int], list[Node]]()
    last_exec_epoch = dict[int, int]()
    for pid, process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
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
            for exid, exec_epoch in process.exec_epochs.items():
                for tid, thread in exec_epoch.threads.items():
                    for op_index, op in enumerate(thread.ops):
                        if op.pthread_id == target_pthread_id:
                            ret.append((pid, exid, tid, op_index))
                        break
        return ret

    def get_last_pthread(pid: int, exid: int, target_pthread_id: int) -> list[Node]:
        ret = list[Node]()
        for pid, process in process_tree_prov_log.processes.items():
            for exid, exec_epoch in process.exec_epochs.items():
                for tid, thread in exec_epoch.threads.items():
                    for op_index, op in list(enumerate(thread.ops))[::-1]:
                        if op.pthread_id == target_pthread_id:
                            ret.append((pid, exid, tid, op_index))
                        break
        return ret

    # Hook up forks/joins
    for node in list(nodes):
        pid, exid, tid, op_index = node
        op_data = process_tree_prov_log.processes[pid].exec_epochs[exid].threads[tid].ops[op_index].data
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

def traverse_hb_for_dfgraph(process_tree_prov_log: ProvLog, starting_node: Node, traversed: set[int] , dataflow_graph:nx.DiGraph, cmd_map: dict[int, list[str]], inode_version_map: dict[int, set[FileVersion]]) -> None:
    starting_pid = starting_node[0]
    
    starting_op = prov_log_get_node(process_tree_prov_log, starting_node[0], starting_node[1], starting_node[2], starting_node[3])
    process_graph = provlog_to_digraph(process_tree_prov_log)
    
    edges = list_edges_from_start_node(process_graph, starting_node)
    name_map = collections.defaultdict[InodeOnDevice, list[pathlib.Path]](list)

    target_nodes = collections.defaultdict[int, list[Node]](list)
    console = rich.console.Console(file=sys.stderr)
    
    for edge in edges:  
        pid, exec_epoch_no, tid, op_index = edge[0]
        
        # check if the process is already visited when waitOp occurred
        if pid in traversed or tid in traversed:
            continue
        
        op = prov_log_get_node(process_tree_prov_log, pid, exec_epoch_no, tid, op_index).data
        next_op = prov_log_get_node(process_tree_prov_log, edge[1][0], edge[1][1], edge[1][2], edge[1][3]).data
        if isinstance(op, OpenOp):
            access_mode = op.flags & os.O_ACCMODE
            processNode = ProcessNode(pid=pid, cmd=tuple(cmd_map[pid]))
            dataflow_graph.add_node(processNode, label=processNode.cmd)
            file = InodeOnDevice(op.path.device_major, op.path.device_minor, op.path.inode)
            path_str = op.path.path.decode("utf-8")
            curr_version = FileVersion(op.path.mtime.sec, op.path.mtime.nsec)
            inode_version_map.setdefault(op.path.inode, set())
            inode_version_map[op.path.inode].add(curr_version)
            fileNode = FileNode(file, curr_version, path_str)
            dataflow_graph.add_node(fileNode, label=fileNode.label)
            path = pathlib.Path(op.path.path.decode("utf-8"))
            if path not in name_map[file]:
                name_map[file].append(path)
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
                traverse_hb_for_dfgraph(process_tree_prov_log, node, traversed, dataflow_graph, cmd_map, inode_version_map)
                traversed.add(node[2])
        # return back to the WaitOp of the parent process
        if isinstance(next_op, WaitOp):
            if next_op.task_id == starting_pid or next_op.task_id == starting_op.pthread_id:
                return

def provlog_to_dataflow_graph(process_tree_prov_log: ProvLog) -> nx.DiGraph:
    dataflow_graph = nx.DiGraph()
    process_graph = provlog_to_digraph(process_tree_prov_log)
    root_node = [n for n in process_graph.nodes() if process_graph.out_degree(n) > 0 and process_graph.in_degree(n) == 0][0]
    traversed: set[int] = set()
    cmd_map = collections.defaultdict[int, list[str]](list)
    for edge in list(nx.edges(process_graph))[::-1]:
        pid, exec_epoch_no, tid, op_index = edge[0]
        op = prov_log_get_node(process_tree_prov_log, pid, exec_epoch_no, tid, op_index).data
        if isinstance(op, ExecOp):
            if pid == tid and exec_epoch_no == 0:
                cmd_map[tid] = [arg.decode(errors="surrogate") for arg in op.argv]

    inode_version_map: dict[int, set[FileVersion]] = {}
    traverse_hb_for_dfgraph(process_tree_prov_log, root_node, traversed, dataflow_graph, cmd_map, inode_version_map)

    file_version: dict[str, int] = {}
    for inode, versions in inode_version_map.items():
        sorted_versions = sorted(versions, key=lambda version: (version.mtime_sec, version.mtime_nsec))
        for idx, version in enumerate(sorted_versions):
            str_id = f"{inode}_{version.mtime_sec}_{version.mtime_nsec}"
            file_version[str_id] = idx

    for idx, node in enumerate(dataflow_graph.nodes()):
        if isinstance(node, FileNode):
            str_id = f"{node.inodeOnDevice.inode}_{node.version.mtime_sec}_{node.version.mtime_nsec}"
            label = f"{node.file} inode {node.inodeOnDevice.inode} fv {file_version[str_id]} "
            nx.set_node_attributes(dataflow_graph, {node: label}, "label")

    return dataflow_graph

def prov_log_get_node(prov_log: ProvLog, pid: int, exec_epoch: int, tid: int, op_no: int) -> Op:
    return prov_log.processes[pid].exec_epochs[exec_epoch].threads[tid].ops[op_no]


def validate_hb_closes(provlog: ProvLog, process_graph: nx.DiGraph) -> list[str]:
    # Note that this test doesn't work if a process "intentionally" leaves a fd open for its child.
    # E.g., bash-in-pipe
    provlog_reverse = process_graph.reverse()
    ret = list[str]()
    reserved_fds = {0, 1, 2}
    for node in process_graph.nodes:
        op = prov_log_get_node(provlog, *node)
        if isinstance(op.data, CloseOp) and op.data.ferrno == 0:
            for closed_fd in range(op.data.low_fd, op.data.high_fd + 1):
                if closed_fd not in reserved_fds:
                    for pred_node in nx.dfs_preorder_nodes(provlog_reverse, node):
                        pred_op = prov_log_get_node(provlog, *pred_node)
                        if isinstance(pred_op.data, OpenOp) and pred_op.data.fd == closed_fd and op.data.ferrno == 0:
                            break
                    else:
                        ret.append(f"Close of {closed_fd} in {node} is not preceeded by corresponding open")
    return ret


def validate_hb_waits(provlog: ProvLog, process_graph: nx.DiGraph) -> list[str]:
    provlog_reverse = process_graph.reverse()
    ret = list[str]()
    for node in process_graph.nodes:
        op = prov_log_get_node(provlog, *node)
        if isinstance(op.data, WaitOp) and op.data.ferrno == 0:
            for pred_node in nx.dfs_preorder_nodes(provlog_reverse, node):
                pred_op = prov_log_get_node(provlog, *pred_node)
                pid1, eid1, tid1, opid1 = pred_node
                if isinstance(pred_op.data, CloneOp) and pred_op.data.task_type == op.data.task_type and pred_op.data.task_id == op.data.task_id and op.data.ferrno == 0:
                    break
            else:
                ret.append(f"Wait of {op.data.task_id} in {node} is not preceeded by corresponding clone")
    return ret

def validate_hb_clones(provlog: ProvLog, process_graph: nx.DiGraph) -> list[str]:
    ret = list[str]()
    for node in process_graph.nodes:
        op = prov_log_get_node(provlog, *node)
        if isinstance(op.data, CloneOp) and op.data.ferrno == 0:
            for node1 in process_graph.successors(node):
                pid1, exid1, tid1, op_no1 = node1
                op1 = prov_log_get_node(provlog, *node1)
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


def validate_hb_degree(provlog: ProvLog, process_graph: nx.DiGraph) -> list[str]:
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


def validate_hb_acyclic(provlog: ProvLog, process_graph: nx.DiGraph) -> list[str]:
    try:
        cycle = nx.find_cycle(process_graph)
    except nx.NetworkXNoCycle:
        return []
    else:
        return [f"Cycle detected: {cycle}"]


def validate_hb_execs(provlog: ProvLog, process_graph: nx.DiGraph) -> list[str]:
    ret = list[str]()
    for node0 in process_graph.nodes():
        pid0, eid0, tid0, op0 = node0
        op0 = prov_log_get_node(provlog, *node0)
        if isinstance(op0.data, ExecOp):
            for node1 in process_graph.successors(node0):
                pid1, eid1, tid1, op1 = node1
                op1 = prov_log_get_node(provlog, *node1)
                if isinstance(op1.data, InitExecEpochOp):
                    if eid0 + 1 != eid1:
                        ret.append(f"ExecOp {node0} is followed by {node1}, whose exec epoch id should be {eid0 + 1}")
                    break
            else:
                ret.append(f"ExecOp {node0} is not followed by an InitExecEpochOp, but by {op1}.")
    return ret


def validate_hb_graph(processes: ProvLog, hb_graph: nx.DiGraph) -> list[str]:
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

def color_hb_graph(prov_log: ProvLog, process_graph: nx.DiGraph) -> None:
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

def provlog_to_process_tree(prov_log: ProvLog) -> nx.DiGraph:
    process_tree = collections.defaultdict(list)
    
    for pid, process in prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            for tid, thread in exec_epoch.threads.items():
                for op_index, op in enumerate(thread.ops):
                    op_data = op.data

                    if isinstance(op_data, CloneOp) and op_data.ferrno == 0:
                        child_pid = op_data.task_id
                        process_tree[pid].append(child_pid)

    G = nx.DiGraph()

    for parent_pid, children in process_tree.items():
        if not G.has_node(parent_pid):
            G.add_node(parent_pid, label=f"Process {parent_pid}")
        for child_pid in children:
            if not G.has_node(child_pid):
                G.add_node(child_pid, label=f"Process {child_pid}")
            G.add_edge(parent_pid, child_pid)

    return G


def get_max_parallelism(ops_graph: nx.DiGraph) -> int:
    max_para = 0
    root_node = [n for n in ops_graph.nodes() if ops_graph.out_degree(n) > 0 and ops_graph.in_degree(n) == 0][0]
    parallel_processes = []
    for idx, nodes in enumerate(nx.bfs_layers(ops_graph, [root_node])):
        if len(nodes) > max_para:
            parallel_processes = []
            for node in nodes:
                parallel_processes.append(node[0])
        max_para = max(max_para, len(nodes))
    print(f"Parallel processes are: {parallel_processes}")
    return max_para