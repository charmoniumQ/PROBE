import collections
import dataclasses
import enum
import os
import pathlib
import rich
import sys
import typing
import warnings
import networkx
import numpy
from .ptypes import TaskType, Pid, ExecNo, Tid, ProbeLog, Inode, InodeVersion, initial_exec_no, Host, Device
from .ops import Op, CloneOp, ExecOp, WaitOp, OpenOp, CloseOp, InitExecEpochOp, InitThreadOp, StatOp
from .graph_utils import list_edges_from_start_node


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


# type alias for a node
OpNode = tuple[Pid, ExecNo, Tid, int]

# type for the edges
EdgeType: typing.TypeAlias = tuple[OpNode, OpNode]


if typing.TYPE_CHECKING:
    HbGraph: typing.TypeAlias = networkx.DiGraph[OpNode]
    DfGraph: typing.TypeAlias = networkx.DiGraph[FileAccess | ProcessNode]
    ProcessTree: typing.TypeAlias = networkx.DiGraph[str]
else:
    HbGraph = networkx.DiGraph
    DfGraph = networkx.DiGraph
    ProcessTree = networkx.DiGraph


def validate_probe_log(
        probe_log: ProbeLog,
) -> list[str]:
    ret = list[str]()
    waited_processes = set[tuple[TaskType, int]]()
    cloned_processes = set[tuple[TaskType, int]]()
    opened_fds = set[int]()
    closed_fds = set[int]()
    for pid, process in probe_log.processes.items():
        epochs = set[int]()
        last_epoch = max(process.execs.keys())
        for exec_epoch_no, exec_epoch in process.execs.items():
            epochs.add(exec_epoch_no)
            first_ee_op_idx = 0
            first_ee_op = exec_epoch.threads[pid.main_thread()].ops[first_ee_op_idx]
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
            threads_ending_in_exec = 0
            for tid, thread in exec_epoch.threads.items():
                first_thread_op_idx = first_ee_op_idx + (1 if tid == pid.main_thread() else 0)
                first_thread_op = thread.ops[first_thread_op_idx]
                if not isinstance(first_thread_op.data, InitThreadOp):
                    ret.append(f"{first_thread_op_idx} in exec_epoch should be InitThreadOp")
                if isinstance(thread.ops[-1], ExecOp):
                    threads_ending_in_exec += 1
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
                        if not op.data.argv:
                            ret.append("No arguments stored in exec syscall")
                    elif isinstance(op.data, CloseOp) and op.data.ferrno == 0:
                        # Range in Python is up-to-not-including high_fd, so we add one to it.
                        closed_fds.update(range(op.data.low_fd, op.data.high_fd + 1))
                    elif isinstance(op.data, CloneOp) and op.data.ferrno == 0:
                        if False:
                            pass
                        elif op.data.task_type == TaskType.TASK_PID and op.data.task_id not in probe_log.processes.keys():
                            ret.append(f"CloneOp returned a PID {op.data.task_id} that we didn't track")
                        elif op.data.task_type == TaskType.TASK_TID and op.data.task_id not in exec_epoch.threads.keys():
                            ret.append(f"CloneOp returned a TID {op.data.task_id} that we didn't track")
                        elif op.data.task_type == TaskType.TASK_PTHREAD and op.data.task_id not in pthread_ids:
                            ret.append(f"CloneOp returned a pthread ID {op.data.task_id} that we didn't track")
                        elif op.data.task_type == TaskType.TASK_ISO_C_THREAD and op.data.task_id not in iso_c_thread_ids:
                            ret.append(f"CloneOp returned a ISO C Thread ID {op.data.task_id} that we didn't track")
            if exec_epoch_no != last_epoch:
                assert threads_ending_in_exec == 1
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
    return ret


def probe_log_to_hb_graph(probe_log: ProbeLog) -> HbGraph:
    # [pid, exec_epoch_no, tid, op_index]
    program_order_edges = list[tuple[OpNode, OpNode]]()
    fork_join_edges = list[tuple[OpNode, OpNode | None]]()
    exec_edges = list[tuple[OpNode, OpNode | None]]()
    nodes = list[OpNode]()
    proc_to_ops = dict[tuple[Pid, ExecNo, Tid], list[OpNode]]()
    last_exec_epoch = dict[Pid, ExecNo]()
    for pid, process in probe_log.processes.items():
        for exec_epoch_no, exec_epoch in process.execs.items():
            # to find the last executing epoch of the process
            last_exec_epoch[pid] = max(last_exec_epoch.get(pid, initial_exec_no), exec_epoch_no)
            # Reduce each thread to the ops we actually care about
            for tid, thread in exec_epoch.threads.items():
                context = (pid, exec_epoch_no, tid)
                ops = list[OpNode]()
                # Filter just the ops we are interested in
                op_index = 0
                for op_index, op in enumerate(thread.ops):
                    ops.append((*context, op_index))
                # Add just those ops to the graph
                nodes.extend(ops)
                program_order_edges.extend(zip(ops[:-1], ops[1:])) 
                # Store these so we can hook up forks/joins between threads
                proc_to_ops[context] = ops
            if(len(ops)!=0):
                last_exec_epoch[pid] = max(last_exec_epoch.get(pid, initial_exec_no), exec_epoch_no)
    # Define helper functions
    def first(pid: Pid, exid: ExecNo, tid: Tid) -> OpNode | None:
        if not proc_to_ops.get((pid, exid, tid)):
            warnings.warn(f"We have no ops for PID={pid}, exec={exid}, TID={tid}, but we know that it occurred.")
            return None
        return proc_to_ops[(pid, exid, tid)][0]

    def last(pid: Pid, exid: ExecNo, tid: Tid) -> OpNode:
        return proc_to_ops[(pid, exid, tid)][-1]

    def get_first_pthread(pid: int, exid: int, target_pthread_id: int) -> list[OpNode]:
        ret = list[OpNode]()
        for pid, process in probe_log.processes.items():
            for exid, exec_epoch in process.execs.items():
                for tid, thread in exec_epoch.threads.items():
                    for op_index, op in enumerate(thread.ops):
                        if op.pthread_id == target_pthread_id:
                            ret.append((pid, exid, tid, op_index))
                        break
        return ret

    def get_last_pthread(pid: int, exid: int, target_pthread_id: int) -> list[OpNode]:
        ret = list[OpNode]()
        for pid, process in probe_log.processes.items():
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
        op_data = probe_log.processes[pid].execs[exid].threads[tid].ops[op_index].data
        target: tuple[Pid, ExecNo, Tid]
        if False:
            pass
        elif isinstance(op_data, CloneOp) and op_data.ferrno == 0:
            if False:
                pass
            elif op_data.task_type == TaskType.TASK_PID:
                # Spawning a thread links to the current PID and exec epoch
                target = (Pid(op_data.task_id), initial_exec_no, Tid(op_data.task_id))
                fork_join_edges.append((node, first(*target)))
            elif op_data.task_type == TaskType.TASK_TID:
                target = (pid, exid, Tid(op_data.task_id))
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
                target = (
                    Pid(op_data.task_id),
                    last_exec_epoch.get(Pid(op_data.task_id), initial_exec_no),
                    Tid(op_data.task_id),
                )
                fork_join_edges.append((last(*target), node))
            elif op_data.task_type == TaskType.TASK_TID:
                target = (pid, exid, Tid(op_data.task_id))
                fork_join_edges.append((last(*target), node))
            elif op_data.ferrno == 0 and op_data.task_type == TaskType.TASK_PTHREAD:
                for dest in get_last_pthread(pid, exid, op_data.task_id):
                    fork_join_edges.append((dest, node))
        elif isinstance(op_data, ExecOp):
            # Exec brings same pid, incremented exid, and main thread
            target = pid, exid.next(), pid.main_thread()
            exec_edges.append((node, first(*target)))

    hb_graph = HbGraph()
    for node in nodes:
        hb_graph.add_node(node)

    def add_edges(edges: typing.Iterable[tuple[OpNode, OpNode | None]], label: EdgeLabel) -> None:
        for node0, node1 in edges:
            if node1:
                hb_graph.add_edge(node0, node1, label=label)
    
    add_edges(program_order_edges, EdgeLabel.PROGRAM_ORDER)
    add_edges(exec_edges, EdgeLabel.EXEC)
    add_edges(fork_join_edges, EdgeLabel.FORK_JOIN)
    return hb_graph


def traverse_hb_for_dfgraph(probe_log: ProbeLog, starting_node: OpNode, traversed: set[int] , dataflow_graph: DfGraph, cmd_map: dict[int, list[str]], inode_version_map: dict[int, set[InodeVersion]], hb_graph: HbGraph) -> None:
    starting_pid = starting_node[0]
    
    starting_op = get_op(probe_log, starting_node[0], starting_node[1], starting_node[2], starting_node[3])
    
    edges = list_edges_from_start_node(hb_graph, starting_node)
    name_map = collections.defaultdict[Inode, list[pathlib.Path]](list)

    target_nodes = collections.defaultdict[int, list[OpNode]](list)
    console = rich.console.Console(file=sys.stderr)

    print("starting at", starting_node, starting_op)
    
    for edge in edges:

        pid, exec_epoch_no, tid, op_index = edge[0]
        
        # check if the process is already visited when waitOp occurred
        if pid in traversed or tid in traversed:
            continue
        
        op = get_op(probe_log, pid, exec_epoch_no, tid, op_index).data
        next_op = get_op(probe_log, edge[1][0], edge[1][1], edge[1][2], edge[1][3]).data
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
                traverse_hb_for_dfgraph(probe_log, node, traversed, dataflow_graph, cmd_map, inode_version_map, hb_graph)
                traversed.add(node[2])
        # return back to the WaitOp of the parent process
        if isinstance(next_op, WaitOp):
            if next_op.task_id == starting_pid or next_op.task_id == starting_op.pthread_id:
                return


def probe_log_to_dataflow_graph(probe_log: ProbeLog) -> DfGraph:
    dataflow_graph = DfGraph()
    hb_graph = probe_log_to_hb_graph(probe_log)
    root_node = [n for n in hb_graph.nodes() if hb_graph.out_degree(n) > 0 and hb_graph.in_degree(n) == 0][0]
    traversed: set[int] = set()
    cmd_map = collections.defaultdict[int, list[str]](list)
    for edge in list(hb_graph.edges())[::-1]:
        pid, exec_epoch_no, tid, op_index = edge[0]
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


def validate_hb_closes(probe_log: ProbeLog, hb_graph: HbGraph) -> list[str]:
    # Note that this test doesn't work if a process "intentionally" leaves a fd open for its child.
    # E.g., bash-in-pipe
    reservse_hb_graph = hb_graph.reverse()
    ret = list[str]()
    reserved_fds = {0, 1, 2}
    for node in hb_graph.nodes():
        op = get_op(probe_log, *node)
        if isinstance(op.data, CloseOp) and op.data.ferrno == 0:
            for closed_fd in range(op.data.low_fd, op.data.high_fd + 1):
                if closed_fd not in reserved_fds:
                    for pred_node in networkx.dfs_preorder_nodes(reservse_hb_graph, node):
                        pred_op = get_op(probe_log, *pred_node)
                        if isinstance(pred_op.data, OpenOp) and pred_op.data.fd == closed_fd and op.data.ferrno == 0:
                            break
                    else:
                        ret.append(f"Close of {closed_fd} in {node} is not preceeded by corresponding open")
    return ret


def validate_hb_waits(probe_log: ProbeLog, hb_graph: HbGraph) -> list[str]:
    reservse_hb_graph = hb_graph.reverse()

    ret = list[str]()
    for node in hb_graph.nodes():
        op = get_op(probe_log, *node)
        if isinstance(op.data, WaitOp) and op.data.ferrno == 0:
            for pred_node in networkx.dfs_preorder_nodes(reservse_hb_graph, node):
                pred_op = get_op(probe_log, *pred_node)
                pid1, eid1, tid1, opid1 = pred_node
                if isinstance(pred_op.data, CloneOp) and pred_op.data.task_type == op.data.task_type and pred_op.data.task_id == op.data.task_id and op.data.ferrno == 0:
                    break
            else:
                ret.append(f"Wait of {op.data.task_id} in {node} is not preceeded by corresponding clone")
    return ret

def validate_hb_clones(probe_log: ProbeLog, hb_graph: HbGraph) -> list[str]:
    ret = list[str]()
    for node in hb_graph.nodes():
        op = get_op(probe_log, *node)
        if isinstance(op.data, CloneOp) and op.data.ferrno == 0:
            for node1 in hb_graph.successors(node):
                pid1, exid1, tid1, op_no1 = node1
                op1 = get_op(probe_log, *node1)
                if False:
                    pass
                elif op.data.task_type == TaskType.TASK_PID:
                    if isinstance(op1.data, InitExecEpochOp):
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


def validate_hb_degree(probe_log: ProbeLog, hb_graph: HbGraph) -> list[str]:
    ret = list[str]()
    found_entry = False
    found_exit = False
    for node in hb_graph.nodes():
        if hb_graph.in_degree(node) == 0:
            if not found_entry:
                found_entry = True
            else:
                ret.append(f"Node {node} has no predecessors")
        if hb_graph.out_degree(node) == 0:
            if not found_exit:
                found_exit = True
            else:
                ret.append(f"Node {node} has no successors")
    if not found_entry:
        ret.append("Found no entry node")
    if not found_exit:
        ret.append("Found no exit node")
    return ret


def validate_hb_acyclic(probe_log: ProbeLog, hb_graph: HbGraph) -> list[str]:
    try:
        cycle = networkx.find_cycle(hb_graph)
    except networkx.NetworkXNoCycle:
        return []
    else:
        return [f"Cycle detected: {cycle}"]


def validate_hb_execs(probe_log: ProbeLog, hb_graph: HbGraph) -> list[str]:
    ret = list[str]()
    for node0 in hb_graph.nodes():
        pid0, eid0, tid0, _ = node0
        op0 = get_op(probe_log, *node0)
        if isinstance(op0.data, ExecOp):
            for node1 in hb_graph.successors(node0):
                pid1, eid1, tid1, _ = node1
                op1 = get_op(probe_log, *node1)
                if isinstance(op1.data, InitExecEpochOp):
                    if eid0 + 1 != eid1:
                        ret.append(f"ExecOp {node0} is followed by {node1}, whose exec epoch id should be {eid0 + 1}")
                    break
            else:
                ret.append(f"ExecOp {node0} is not followed by an InitExecEpochOp, but by {op1}.")
    return ret


def validate_hb_graph(processes: ProbeLog, hb_graph: HbGraph) -> list[str]:
    ret = list[str]()
    # ret.extend(validate_hb_closes(processes, hb_graph))
    ret.extend(validate_hb_waits(processes, hb_graph))
    ret.extend(validate_hb_clones(processes, hb_graph))
    ret.extend(validate_hb_degree(processes, hb_graph))
    ret.extend(validate_hb_acyclic(processes, hb_graph))
    ret.extend(validate_hb_execs(processes, hb_graph))
    return ret


def color_hb_graph(probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    label_color_map = {
        EdgeLabel.EXEC: 'yellow',
        EdgeLabel.FORK_JOIN: 'red',
        EdgeLabel.PROGRAM_ORDER: 'green',
    }

    for node0, node1, attrs in hb_graph.edges(data=True):
        label: EdgeLabel = attrs['label']
        hb_graph[node0][node1]['color'] = label_color_map[label]
        del attrs['label']

    for node, data in hb_graph.nodes(data=True):
        pid, exid, tid, op_no = node
        op = get_op(probe_log, *node)
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
        pid, exec_epoch_no, tid, op_index = node
        if(parent):
            parent_pid, parent_exec_epoch_no, parent_tid, parent_op_index = parent
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
