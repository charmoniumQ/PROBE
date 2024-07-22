import typing
import networkx as nx
from .parse_probe_log import ProvLog, Op, CloneOp, ExecOp, WaitOp, OpenOp, CloseOp ,CLONE_THREAD
from enum import IntEnum

class EdgeLabels(IntEnum):
    PROGRAM_ORDER = 1
    FORK_JOIN = 2
    EXEC = 3

def provlog_to_digraph(process_tree_prov_log: ProvLog) -> nx.DiGraph:
    # [pid, exec_epoch_no, tid, op_index]
    Node: typing.TypeAlias = tuple[int, int, int, int]
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
                for op in thread.ops:
                    if isinstance(op.data, CloneOp | ExecOp | WaitOp | OpenOp | CloseOp):
                        ops.append((*context, op_index))
                    op_index+=1

                nodes.extend(ops)
                program_order_edges.extend(zip(ops[:-1], ops[1:]))
                
                # Store these so we can hook up forks/joins between threads
                proc_to_ops[context] = ops
                if len(ops) != 0:
                    # to mark the end of the thread, edge from last op to (pid, -1, tid, -1)
                    program_order_edges.append((proc_to_ops[(pid, exec_epoch_no, tid)][-1], (pid, -1, tid, -1)))

    def first(pid: int, exid: int, tid: int) -> Node:
        if not proc_to_ops.get((pid, exid, tid)):
            entry_node = (pid, exid, tid, -1)
            # as Op object is not available, op_index will be -1
            proc_to_ops[(pid, exid, tid)] = [entry_node]
            nodes.append(entry_node)
            return entry_node
        else:
            return proc_to_ops[(pid, exid, tid)][0]

    def last(pid: int, exid: int, tid: int) -> Node:
        if not proc_to_ops.get((pid, exid, tid)):
            # as Op object is not availaible, op_index will be -1
            exit_node = (pid, exid, tid, -1)
            proc_to_ops[(pid, exid, tid)] = [exit_node]
            nodes.append(exit_node)
            return exit_node
        else:
            return proc_to_ops[(pid, exid, tid)][-1]

    # Hook up forks/joins
    for node in list(nodes):
        pid, exid, tid, op_index = node
        op = process_tree_prov_log.processes[pid].exec_epochs[exid].threads[tid].ops[op_index].data
        if isinstance(op, CloneOp):
            if op.flags & CLONE_THREAD:
                # Spawning a thread links to the current PID and exec epoch
                target = (pid, exid, op.task_id)
            else:
                # New process always links to exec epoch 0 and main thread
                # THe TID of the main thread is the same as the PID
                target = (op.task_id, 0, op.task_id)
            exec_edges.append((node, first(*target)))
        elif isinstance(op, WaitOp) and op.ferrno == 0 and op.task_id > 0:
            # Always wait for main thread of the last exec epoch
            if op.ferrno == 0:
                target = (op.task_id, last_exec_epoch.get(op.task_id, 0), op.task_id)
                fork_join_edges.append((last(*target), node))
        elif isinstance(op, ExecOp):
            # Exec brings same pid, incremented exid, and main thread
            target = pid, exid + 1, pid
            fork_join_edges.append((node, first(*target)))
            
    # Make the main thread exit at the same time as each thread
    for pid, process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            for tid, thread in exec_epoch.threads.items():
                if tid != 0:
                    fork_join_edges.append((last(pid, exec_epoch_no, tid), last(pid, exec_epoch_no, 0)))

    process_graph = nx.DiGraph()
    for node in nodes:
        process_graph.add_node(node)

    def add_edges(edges:list[tuple[Node, Node]], label:EdgeLabels):
        for node0, node1 in edges:
            process_graph.add_edge(node0, node1, label=label)
    
    add_edges(program_order_edges, EdgeLabels.PROGRAM_ORDER)
    add_edges(exec_edges, EdgeLabels.EXEC)
    add_edges(fork_join_edges, EdgeLabels.FORK_JOIN)
    return process_graph

def provlog_to_dataflow_graph(process_tree_prov_log: ProvLog) -> nx.DiGraph:
    dataflow_graph = nx.DiGraph()
    O_ACCMODE = 0x3
    class NodeType(IntEnum):
        FILE = 0
        PROCESS = 1
    # print(process_tree_prov_log)
    for pid, process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            for tid, thread in exec_epoch.threads.items():
                for op in thread.ops:
                    op = op.data
                    # [nodeType, name, mode]
                    FileNode: typing.TypeAlias = tuple[int, str, int]
                    # [nodeType, tid]
                    ProcessNode: typing.TypeAlias = tuple[int, int]
                    if isinstance(op, OpenOp):
                        access_mode = op.flags & O_ACCMODE
                        processNode = ProcessNode(((int)(NodeType.PROCESS), pid))
                        fileNode = FileNode(((int)(NodeType.FILE), op.path.path, access_mode))
                        if access_mode == 0 or access_mode == 2:
                            access_mode_str = "O_RDONLY (read-only)" 
                            dataflow_graph.add_edge(fileNode, processNode)
                        elif access_mode == 1 or access_mode == 2:
                            dataflow_graph.add_edge(processNode, fileNode)
                            access_mode_str = "O_WRONLY (write-only)"
                        else:
                            raise Exception("unknown access mode")

                    elif isinstance(op, CloneOp):
                        processNode1 = ProcessNode(((int)(NodeType.PROCESS), pid))
                        processNode2 = ProcessNode(((int)(NodeType.PROCESS), op.task_id))
                        dataflow_graph.add_edge(processNode1, processNode2)
    
    pydot_graph = nx.drawing.nx_pydot.to_pydot(dataflow_graph)
    dot_string = pydot_graph.to_string()
    print(dot_string)

def digraph_to_pydot_string(process_graph: nx.DiGraph) -> str:
    label_color_map = {
    EdgeLabels.EXEC: 'yellow',
    EdgeLabels.FORK_JOIN: 'red',
    EdgeLabels.PROGRAM_ORDER: 'green',
    }

    for node0, node1, attrs in process_graph.edges(data=True):
        label:EdgeLabels = attrs['label']
        process_graph[node0][node1]['color'] = label_color_map[label]
    pydot_graph = nx.drawing.nx_pydot.to_pydot(process_graph)
    dot_string = pydot_graph.to_string()
    return dot_string


def construct_process_graph(process_tree_prov_log: ProvLog) -> str:
    """
    Construct a happens-before graph from process_tree_prov_log

    The graph shows the order that prov ops happen.
    """

    process_graph = provlog_to_digraph(process_tree_prov_log)
    return digraph_to_pydot_string(process_graph)