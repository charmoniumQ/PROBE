import typing
import networkx as nx
from .parse_probe_log import ProcessTreeProvLog, Op, CloneOp, ExecOp, WaitOp, CLONE_THREAD

def construct_process_graph(process_tree_prov_log: ProcessTreeProvLog):
    """
    Construct a happens-before graph from process_tree_prov_log

    The graph shows the order that prov ops happen.
    """
    # [pid, exec_epoch_no, tid, Op | str, node_count, op_index, _time]
    Node: typing.TypeAlias = tuple[int, int, int, Op | str, int, int, int]
    nodes = list[Node]()
    program_order_edges = list[tuple[Node, Node]]()
    proc_to_ops = dict[tuple[int, int, int], list[Node]]()
    last_exec_epoch = dict[int, int]()
    global node_count
    node_count = int(1)
    for (pid, _time), process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            # to find the last executing epoch of the process
            last_exec_epoch[pid] = max(last_exec_epoch.get(pid, 0), exec_epoch_no)

            # Reduce each thread to the ops we actually care about
            for tid, thread in exec_epoch.threads.items():
                context = (pid, exec_epoch_no, tid)
                ops = list[tuple[int, int, int, Op | str, int, int, int]]()
                
                # Filter just the ops we are interested in
                op_index = 0
                
                for op in thread.ops:
                    if isinstance(op.data, CloneOp | ExecOp | WaitOp):
                        ops.append((*context, op.data, node_count, op_index, _time))
                        node_count+=1
                    op_index+=1

                nodes.extend(ops)
                program_order_edges.extend(zip(ops[:-1], ops[1:]))
                
                # Store these so we can hook up forks/joins between threads
                proc_to_ops[context] = ops

    def first(pid: int, _time:int, exid: int, tid: int) -> Op:
        global node_count
        if not proc_to_ops.get((pid, exid, tid)):
            entry_node = (pid, exid, tid, "<entry>", node_count, -1, _time)
            node_count = node_count+1
            # as Op object is not available, op_index will be -1
            proc_to_ops[(pid, exid, tid)] = [entry_node]
            nodes.append(entry_node)
            return entry_node
        else:
            return proc_to_ops[(pid, exid, tid)][0]

    def last(pid: int, _time:int, exid: int, tid: int) -> Node:
        global node_count
        if not proc_to_ops.get((pid, exid, tid)):
            # as Op object is not availaible, op_index will be -1
            exit_node = (pid, exid, tid, "<exit>", node_count , -1, _time)
            node_count = node_count+1
            proc_to_ops[(pid, exid, tid)] = [exit_node]
            nodes.append(exit_node)
            return exit_node
        else:
            return proc_to_ops[(pid, exid, tid)][-1]

    fork_join_edges = list[tuple[Node, Node]]()
    exec_edges = list[tuple[Node, Node]]()

    # Hook up forks/joins
    for node in list(nodes):
        pid, exid, tid, op, node_id, op_index, _time = node
        if isinstance(op, CloneOp):
            if op.flags & CLONE_THREAD:
                # Spawning a thread links to the current PID and exec epoch
                target = (pid, _time, exid, op.child_thread_id)
            else:
                # New process always links to exec epoch 0 and thread 0
                target = (op.child_process_id, -1, 0, 0)
            # is clone happens link the node to the first node of the next process/thread
            exec_edges.append((node, first(*target)))
        elif isinstance(op, WaitOp) and op.ferrno == 0 and op.ret > 0:
            # Always wait for thread 0 of the last exec epoch
            if op.ferrno == 0:
                target = (op.ret, -1, last_exec_epoch.get(op.ret, 0), 0)
                fork_join_edges.append((last(*target), node))
        elif isinstance(op, ExecOp):
            # Exec brings same pid, incremented exid, and main thread
            target = pid, _time, exid + 1, 0
            fork_join_edges.append((node, first(*target)))

    # Make the main thread exit at the same time as each thread
    for (pid, _time), process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            for tid, thread in exec_epoch.threads.items():
                if tid != 0:
                    fork_join_edges.append((last(pid, _time, exec_epoch_no, tid), last(pid, _time, exec_epoch_no, 0)))

    process_graph = nx.DiGraph()
    
    for node in nodes:
        # op = [pid, _time, exec_id, tid, op_index]
        process_graph.add_node(node[4], op = [node[0], node[6], node[1],node[2],node[5]])
    
    for node0, node1 in program_order_edges:
        process_graph.add_edge(node0[4], node1[4], color = 'green')
    
    for node0, node1 in exec_edges:
        process_graph.add_edge(node0[4], node1[4], color = 'yellow')

    for node0, node1 in fork_join_edges:
        process_graph.add_edge(node0[4], node1[4], color='red')

    return nx.drawing.nx_pydot.write_dot(process_graph,"./processgraph")