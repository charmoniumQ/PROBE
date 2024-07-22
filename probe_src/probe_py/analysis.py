import typing
import networkx as nx  # type: ignore
from .parse_probe_log import Op, ProvLog, CloneOp, ExecOp, WaitOp, OpenOp, CloseOp, TaskType, InitProcessOp, InitExecEpochOp, InitThreadOp, CLONE_THREAD
from enum import IntEnum


class EdgeLabels(IntEnum):
    PROGRAM_ORDER = 1
    FORK_JOIN = 2
    EXEC = 3


def validate_provlog(
        provlog: ProvLog,
) -> list[str]:
    ret = list[str]()
    waited_processes = set[tuple[TaskType, int]]()
    cloned_processes = set[tuple[TaskType, int]]()
    opened_fds = set[int]()
    closed_fds = set[int]()
    for pid, process in provlog.processes.items():
        epochs = set[int]()
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            epochs.add(exec_epoch_no)
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
                for op in thread.ops:
                    if False:
                        pass
                    elif isinstance(op.data, WaitOp) and op.data.ferrno == 0:
                        waited_processes.add((op.data.task_type, op.data.task_id))
                    elif isinstance(op.data, CloneOp) and op.data.ferrno == 0:
                        cloned_processes.add((op.data.task_type, op.data.task_id))
                    elif isinstance(op.data, OpenOp) and op.data.ferrno == 0:
                        opened_fds.add(op.data.fd)
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
        expected_epochs = set(range(0, max(epochs)))
        if epochs - expected_epochs:
            ret.append(f"Missing epochs for pid={pid}: {sorted(epochs - expected_epochs)}")
    reserved_fds = {0, 1, 2}
    if False:
        pass
    elif closed_fds - opened_fds - reserved_fds:
        ret.append(f"Closed more fds than we opened: {closed_fds - opened_fds - reserved_fds}")
    elif waited_processes - cloned_processes:
        ret.append(f"Waited on more processes than we cloned: {waited_processes - cloned_processes}")
    return ret


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
        if False:
            pass
        elif isinstance(op, CloneOp) and op.data.ferrno == 0:
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

    def add_edges(edges:list[tuple[Node, Node]], label:EdgeLabels) -> None:
        for node0, node1 in edges:
            process_graph.add_edge(node0, node1, label=label)
    
    add_edges(program_order_edges, EdgeLabels.PROGRAM_ORDER)
    add_edges(exec_edges, EdgeLabels.EXEC)
    add_edges(fork_join_edges, EdgeLabels.FORK_JOIN)
    return process_graph


def prov_log_get_node(prov_log: ProvLog, pid: int, exec_epoch: int, tid: int, op_no: int) -> Op:
    return prov_log.processes[pid].exec_epochs[exec_epoch].threads[tid].ops[op_no]


def validate_hb_graph(provlog: ProvLog, process_graph: nx.DiGraph) -> list[str]:
    ret = list[str]()
    provlog_reverse = process_graph.reverse()
    found_entry = False
    found_exit = False
    for node in process_graph.nodes:
        op = prov_log_get_node(provlog, *node) if node[-1] != -1 else None
        if op is None:
            pass
        elif isinstance(op.data, CloseOp) and op.data.ferrno == 0:
            for closed_fd in range(op.data.low_fd, op.data.high_fd + 1):
                for pred_node in nx.dfs_preorder_nodes(provlog_reverse, node):
                    pred_op = prov_log_get_node(provlog, *pred_node) if pred_node[-1] != -1 else None
                    if isinstance(pred_op.data, OpenOp) and pred_op.data.fd == closed_fd and op.data.ferrno == 0:
                        break
                else:
                    ret.append(f"Close of {closed_fd} is not preceeded by corresponding open")
        elif isinstance(op.data, WaitOp) and op.data.ferrno == 0:
            for pred_node in nx.dfs_preorder_nodes(provlog_reverse, node):
                pred_op = prov_log_get_node(provlog, *pred_node) if pred_node[-1] != -1 else None
                if isinstance(pred_op.data, CloneOp) and pred_op.data.task_type == op.data.task_type and pred_op.data.task_id == op.data.task_type and op.data.ferrno == 0:
                    break
            else:
                ret.append(f"Close of {closed_fd} is not preceeded by corresponding open")
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
        ret.append(f"Found no entry node")
    if not found_exit:
        ret.append(f"Found no exit node")
    for (node0, node1) in process_graph.edges:
        pid0, eid0, tid0, op0 = node0
        pid1, eid1, tid1, op1 = node1
        op0 = prov_log_get_node(provlog, *node0) if node0[-1] != -1 else None
        op1 = prov_log_get_node(provlog, *node1) if node1[-1] != -1 else None
        if op0 is None:
            pass
        elif isinstance(op0.data, ExecOp):
            if eid0 + 1 != eid1:
                ret.append(f"ExecOp {node0} is followed by {node1}, whose exec epoch id should be {eid0 + 1}")
            if op1 is None or not isinstance(op1.data, InitExecEpochOp):
                ret.append(f"ExecOp {node0} is followed by {op1}, which is not InitExecEpoch")
        elif isinstance(op0.data, CloneOp) and op0.data.ferrno == 0:
            if False:
                pass
            elif op0.data.task_type == TaskType.TASK_PID:
                if op1 is None or not isinstance(op1.data, InitProcessOp):
                    ret.append(f"CloneOp {node0} with TASK_PID is followed by {node1} which is not InitProcessOp")
                if op0.data.task_id != pid1:
                    ret.append(f"CloneOp {node0} returns {op0.data.task_id} but the next op has pid {pid1}")
            elif op0.data.task_type == TaskType.TASK_TID:
                if op1 is None or not isinstance(op1.data, InitThreadOp):
                    ret.append(f"CloneOp {node0} with TASK_TID is followed by {node1} which is not InitThreadOp")
                if op1 is None or not isinstance(op1.data, InitThreadOp):
                    ret.append(f"CloneOp {node0} returns {op0.data.task_id} but the next op has tid {tid1}")
            elif op0.data.task_type == TaskType.PTHREAD_PID:
                if op1 is None or not op1.pthread_id != op0.data.task_id:
                    ret.append(f"CloneOp {node0} with TASK_PTHREAD is followed by {node1} which has a different pthread_id")
            elif op0.data.task_type == TaskType.ISO_C_THREAD_PID:
                if op1 is None or not op1.iso_c_thread_id != op0.data.task_id:
                    ret.append(f"CloneOp {node0} with TASK_ISO_C_THREAD is followed by {node1} which has a different pthread_id")
    try:
        cycle = nx.find_cycle(process_graph)
    except nx.NetworkXNoCycle:
        pass
    else:
        ret.append(f"Cycle detected: {cycle}")
    return ret


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
    dot_string = typing.cast(str, pydot_graph.to_string())
    return dot_string


def construct_process_graph(process_tree_prov_log: ProvLog) -> str:
    """
    Construct a happens-before graph from process_tree_prov_log

    The graph shows the order that prov ops happen.
    """

    process_graph = provlog_to_digraph(process_tree_prov_log)
    return digraph_to_pydot_string(process_graph)
