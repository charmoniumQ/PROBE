import typing
import networkx as nx
from .parse_probe_log import ProvLog, Op, CloneOp, ExecOp, WaitOp, CLONE_THREAD

# [pid, exec_epoch_no, tid, Op | str, op_index]
Node: typing.TypeAlias = tuple[int, int, int, Op | str, int]
program_order_edges = list[tuple[Node, Node]]()
fork_join_edges = list[tuple[Node, Node]]()
exec_edges = list[tuple[Node, Node]]()

def provlog_to_digraph(process_tree_prov_log: ProvLog) -> nx.DiGraph:
    nodes = list[Node]()
    # program_order_edges = list[tuple[Node, Node]]()
    proc_to_ops = dict[tuple[int, int, int], list[Node]]()
    last_exec_epoch = dict[int, int]()    
    for (pid), process in process_tree_prov_log.processes.items():
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
                    if isinstance(op.data, CloneOp | ExecOp | WaitOp):
                        ops.append((*context, op.data, op_index))
                    op_index+=1

                nodes.extend(ops)
                program_order_edges.extend(zip(ops[:-1], ops[1:]))
                
                # Store these so we can hook up forks/joins between threads
                proc_to_ops[context] = ops

    def first(pid: int, exid: int, tid: int) -> Op:
        if not proc_to_ops.get((pid, exid, tid)):
            entry_node = (pid, exid, tid, "<entry>", -1)
            # as Op object is not available, op_index will be -1
            proc_to_ops[(pid, exid, tid)] = [entry_node]
            nodes.append(entry_node)
            return entry_node
        else:
            return proc_to_ops[(pid, exid, tid)][0]

    def last(pid: int, exid: int, tid: int) -> Node:
        if not proc_to_ops.get((pid, exid, tid)):
            # as Op object is not availaible, op_index will be -1
            exit_node = (pid, exid, tid, "<exit>", -1)
            proc_to_ops[(pid, exid, tid)] = [exit_node]
            nodes.append(exit_node)
            return exit_node
        else:
            return proc_to_ops[(pid, exid, tid)][-1]

    # Hook up forks/joins
    for node in list(nodes):
        pid, exid, tid, op, op_index = node
        if isinstance(op, CloneOp):
            if op.flags & CLONE_THREAD:
                # Spawning a thread links to the current PID and exec epoch
                target = (pid, exid, op.child_thread_id)
            else:
                target = (op.child_process_id, 0, 0)
            exec_edges.append((node, first(*target)))
        elif isinstance(op, WaitOp) and op.ferrno == 0 and op.ret > 0:
            # Always wait for main thread of the last exec epoch
            if op.ferrno == 0:
                target = (op.ret, -1, last_exec_epoch.get(op.ret, 0), op.ret)
                fork_join_edges.append((last(*target), node))
        elif isinstance(op, ExecOp):
            # Exec brings same pid, incremented exid, and main thread
            target = pid, exid + 1, 0
            fork_join_edges.append((node, first(*target)))
            
    # Make the main thread exit at the same time as each thread
    for (pid), process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            for tid, thread in exec_epoch.threads.items():
                if tid != 0:
                    fork_join_edges.append((last(pid, exec_epoch_no, tid), last(pid, exec_epoch_no, 0)))

    process_graph = nx.DiGraph()
    for node in nodes:
        process_graph.add_node((node[0], node[1], node[2], node[4]))

    def add_edges(graph, edges):
        for node0, node1 in edges:
            node_0 = (node0[0], node0[1], node0[2], node0[4])
            node_1 = (node1[0], node1[1], node1[2], node1[4])
            graph.add_edge(node_0, node_1)
    
    add_edges(process_graph, program_order_edges)
    add_edges(process_graph, exec_edges)
    add_edges(process_graph, fork_join_edges)
    return process_graph

def digraph_to_pydot_string(process_graph: nx.DiGraph) -> str:
    def add_color_to_edges(graph, edges, color):
        for node0, node1 in edges:
            node_0 = (node0[0], node0[1], node0[2], node0[4])
            node_1 = (node1[0], node1[1], node1[2], node1[4])
            graph[node_0][node_1]['color'] = color
    
    add_color_to_edges(process_graph, program_order_edges, 'green')
    add_color_to_edges(process_graph, exec_edges, 'yellow')
    add_color_to_edges(process_graph, fork_join_edges, 'red')
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