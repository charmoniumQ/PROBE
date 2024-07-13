import typing
import networkx as nx
from .parse_probe_log import ProvLog, Op, CloneOp, ExecOp, WaitOp, OpenOp, CloneOp, CloseOp, CLONE_THREAD, TaskType
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
        
    def get_first_pthread(pid, exid, target_pthread_id):
        for kthread_id, thread in process_tree_prov_log.processes[pid].exec_epochs[exid].threads.items():          
            op_index = 0
            for op in thread.ops:               
                if op.pthread_id == target_pthread_id:
                    return (pid, exid, kthread_id, op_index)
                op_index+=1  
        return (pid, -1, target_pthread_id, -1) 

    def get_last_pthread(pid, exid, target_pthread_id):
        for kthread_id, thread in process_tree_prov_log.processes[pid].exec_epochs[exid].threads.items():          
            op_index = len(thread.ops) - 1
            ops = thread.ops
            while op_index >= 0:  
                op = ops[op_index]             
                if op.pthread_id == target_pthread_id:
                    return (pid, exid, kthread_id, op_index)
                op_index-=1
        return (pid, -1, target_pthread_id, -1)

    # Hook up forks/joins
    for node in list(nodes):
        pid, exid, tid, op_index = node
        op = process_tree_prov_log.processes[pid].exec_epochs[exid].threads[tid].ops[op_index].data
        global target
        if isinstance(op, CloneOp):
            if op.task_type == TaskType.TASK_PID:
                # Spawning a thread links to the current PID and exec epoch
                target = (pid, exid, op.task_id)
            if op.task_type == TaskType.TASK_PTHREAD:
                target_pthread_id = op.task_id
                dest = get_first_pthread(pid, exid, target_pthread_id)
                fork_join_edges.append((node, dest))
                continue
            else:
                # New process always links to exec epoch 0 and main thread
                # THe TID of the main thread is the same as the PID
                target = (op.task_id, 0, op.task_id)
            exec_edges.append((node, first(*target)))
        elif isinstance(op, WaitOp) and op.ferrno == 0 and op.task_id > 0:
            # Always wait for main thread of the last exec epoch
            if op.ferrno == 0 and (op.task_type == TaskType.TASK_PID or op.task_type == TaskType.TASK_TID):
                target = (op.task_id, last_exec_epoch.get(op.task_id, 0), op.task_id)
                fork_join_edges.append((last(*target), node))
            elif op.ferrno == 0 and op.task_type == TaskType.TASK_PTHREAD:
                fork_join_edges.append((get_last_pthread(pid, exid, op.task_id), node))
        elif isinstance(op, ExecOp):
            # Exec brings same pid, incremented exid, and main thread
            target = pid, exid + 1, pid
            fork_join_edges.append((node, first(*target)))
            
    # Make the main thread exit at the same time as each thread
    for pid, process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            for tid, thread in exec_epoch.threads.items():
                if tid != pid:
                    fork_join_edges.append((last(pid, exec_epoch_no, tid), last(pid, exec_epoch_no, pid)))

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