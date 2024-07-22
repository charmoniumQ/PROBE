import typing
import networkx as nx  # type: ignore
from .parse_probe_log import Op, ProvLog, CloneOp, ExecOp, WaitOp, OpenOp, CloseOp, TaskType, InitProcessOp, InitExecEpochOp, InitThreadOp
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
                        if op.data.task_type == TaskType.TASK_PID:
                            # New process implicitly also creates a new thread
                            cloned_processes.add((TaskType.TASK_TID, op.data.task_id))
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
        expected_epochs = set(range(0, max(epochs) + 1))
        if expected_epochs - epochs:
            ret.append(f"Missing epochs for pid={pid}: {sorted(epochs - expected_epochs)}")
    reserved_fds = {0, 1, 2}
    if False:
        pass
    elif closed_fds - opened_fds - reserved_fds:
        ret.append(f"Closed more fds than we opened: {closed_fds - reserved_fds=} {opened_fds=}")
    elif waited_processes - cloned_processes:
        ret.append(f"Waited on more processes than we cloned: {waited_processes=} {cloned_processes=}")
    return ret


# TODO: Rename "digraph" to "hb_graph" in the entire project.
# Digraph (aka "directed graph") is too vague a term; the proper name is "happens-before graph".
# Later on, we will have a function that transforms an hb graph to file graph (both of which are digraphs)
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
        return ret

    def get_last_pthread(pid: int, exid: int, target_pthread_id: int) -> list[Node]:
        ret = list[Node]()
        for pid, process in process_tree_prov_log.processes.items():
            for exid, exec_epoch in process.exec_epochs.items():
                for tid, thread in exec_epoch.threads.items():
                    for op_index, op in list(enumerate(thread.ops))[::-1]:
                        if op.pthread_id == target_pthread_id:
                            ret.append((pid, exid, tid, op_index))
        return ret

    # Hook up forks/joins
    for node in list(nodes):
        pid, exid, tid, op_index = node
        op = process_tree_prov_log.processes[pid].exec_epochs[exid].threads[tid].ops[op_index].data
        target: tuple[int, int, int]
        if False:
            pass
        elif isinstance(op, CloneOp) and op.ferrno == 0:
            if False:
                pass
            elif op.task_type == TaskType.TASK_PID:
                # Spawning a thread links to the current PID and exec epoch
                target = (op.task_id, 0, op.task_id)
                fork_join_edges.append((node, first(*target)))
            elif op.task_type == TaskType.TASK_TID:
                target = (pid, exid, op.task_id)
                fork_join_edges.append((node, first(*target)))
            elif op.task_type == TaskType.TASK_PTHREAD:
                for dest in get_first_pthread(pid, exid, op.task_id):
                    fork_join_edges.append((node, dest))
            else:
                raise RuntimeError(f"Task type {op.task_type} supported")
        elif isinstance(op, WaitOp) and op.ferrno == 0 and op.task_id > 0:
            if False:
                pass
            elif op.task_type == TaskType.TASK_PID:
                target = (op.task_id, last_exec_epoch.get(op.task_id, 0), op.task_id)
                fork_join_edges.append((last(*target), node))
            elif op.task_type == TaskType.TASK_TID:
                target = (pid, exid, op.task_id)
                fork_join_edges.append((last(*target), node))
            elif op.ferrno == 0 and op.task_type == TaskType.TASK_PTHREAD:
                for dest in get_last_pthread(pid, exid, op.task_id):
                    fork_join_edges.append((dest, node))
        elif isinstance(op, ExecOp):
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


def prov_log_get_node(prov_log: ProvLog, pid: int, exec_epoch: int, tid: int, op_no: int) -> Op:
    return prov_log.processes[pid].exec_epochs[exec_epoch].threads[tid].ops[op_no]


def validate_hb_graph(provlog: ProvLog, process_graph: nx.DiGraph) -> list[str]:
    ret = list[str]()
    provlog_reverse = process_graph.reverse()
    found_entry = False
    found_exit = False
    reserved_fds = {0, 1, 2}
    for node in process_graph.nodes:
        op = prov_log_get_node(provlog, *node)
        if False:
            pass
        elif isinstance(op.data, CloseOp) and op.data.ferrno == 0:
            for closed_fd in range(op.data.low_fd, op.data.high_fd + 1):
                if closed_fd not in reserved_fds:
                    for pred_node in nx.dfs_preorder_nodes(provlog_reverse, node):
                        pred_op = prov_log_get_node(provlog, *pred_node)
                        if isinstance(pred_op.data, OpenOp) and pred_op.data.fd == closed_fd and op.data.ferrno == 0:
                            break
                    else:
                        ret.append(f"Close of {closed_fd} is not preceeded by corresponding open")
        elif isinstance(op.data, WaitOp) and op.data.ferrno == 0:
            for pred_node in nx.dfs_preorder_nodes(provlog_reverse, node):
                pred_op = prov_log_get_node(provlog, *pred_node)
                pid1, eid1, tid1, opid1 = pred_node
                if isinstance(pred_op.data, CloneOp) and pred_op.data.task_type == op.data.task_type and pred_op.data.task_id == op.data.task_type and op.data.ferrno == 0:
                    break
            else:
                ret.append(f"Close of {closed_fd} in {node} is not preceeded by corresponding open")
        elif isinstance(op.data, CloneOp) and op.data.ferrno == 0:
            for node1 in process_graph.successors(node):
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
                elif op.data.task_type == TaskType.TASK_PTHREAD_ID and op.data.task_id == op1.pthread_id:
                    break
                elif op.data.task_type == TaskType.TASK_ISO_C_THREAD_ID and op.data.task_id == op1.iso_c_thread_id:
                    break
            else:
                ret.append(f"Could not find a successor for CloneOp {node} {op.data.task_type} in the target thread")
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
    for (node0, node1) in process_graph.edges:
        pid0, eid0, tid0, op0 = node0
        pid1, eid1, tid1, op1 = node1
        op0 = prov_log_get_node(provlog, *node0)
        op1 = prov_log_get_node(provlog, *node1)
        if False:
            pass
        elif isinstance(op0.data, ExecOp):
            if eid0 + 1 != eid1:
                ret.append(f"ExecOp {node0} is followed by {node1}, whose exec epoch id should be {eid0 + 1}")
            if not isinstance(op1.data, InitExecEpochOp):
                ret.append(f"ExecOp {node0} is followed by {node1}, which is not InitExecEpoch")
    try:
        cycle = nx.find_cycle(process_graph)
    except nx.NetworkXNoCycle:
        pass
    else:
        ret.append(f"Cycle detected: {cycle}")
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


def digraph_to_pydot_string(prov_log: ProvLog, process_graph: nx.DiGraph) -> str:

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
            data["label"] += f"\nopen{op.data.path.path} (fd={op.data.fd})"
        elif isinstance(op.data, CloseOp):
            fds = list(range(op.data.low_fd, op.data.high_fd + 1))
            data["label"] += "\nclose" + " ".join(map(str, fds))

    pydot_graph = nx.drawing.nx_pydot.to_pydot(process_graph)
    dot_string = typing.cast(str, pydot_graph.to_string())
    return dot_string


def construct_process_graph(process_tree_prov_log: ProvLog) -> str:
    """
    Construct a happens-before graph from process_tree_prov_log

    The graph shows the order that prov ops happen.
    """

    process_graph = provlog_to_digraph(process_tree_prov_log)
    return digraph_to_pydot_string(process_tree_prov_log, process_graph)
