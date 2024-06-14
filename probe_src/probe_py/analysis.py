import typing
import networkx
from .parse_probe_log import ProvLog, Op, CloneOp, ExecOp, WaitOp, CLONE_THREAD


def construct_process_graph(process_tree_prov_log: ProvLog) -> str:
    """
    Construct a happens-before graph from process_tree_prov_log

    The graph shows the order that prov ops happen.
    """
    Node: typing.TypeAlias = tuple[int, int, int, Op | str]
    nodes = list[Node]()
    program_order_edges = list[tuple[Node, Node]]()
    proc_to_ops = dict[tuple[int, int, int], list[Node]]()
    last_exec_epoch = dict[int, int]()

    for pid, process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            last_exec_epoch[pid] = max(last_exec_epoch.get(pid, 0), exec_epoch_no)

            # Reduce each thread to the ops we actually care about
            for tid, thread in exec_epoch.threads.items():
                context = (pid, exec_epoch_no, tid)

                # Filter just the ops we are interested in
                ops = [
                    (*context, op.data)
                    for op in thread.ops
                    if isinstance(op.data, CloneOp | ExecOp | WaitOp)
                ]

                nodes.extend(ops)
                program_order_edges.extend(zip(ops[:-1], ops[1:]))

                # Store these so we can hook up forks/joins between threads
                proc_to_ops[context] = ops

    def first(pid: int, exid: int, tid: int) -> Op:
        if not proc_to_ops.get((pid, exid, tid)):
            entry_node = (pid, exid, tid, "<entry>")
            proc_to_ops[(pid, exid, tid)] = [entry_node]
            nodes.append(entry_node)
            return entry_node
        else:
            return proc_to_ops[(pid, exid, tid)][0]

    def last(pid: int, exid: int, tid: int) -> Node:
        if not proc_to_ops.get((pid, exid, tid)):
            exit_node = (pid, exid, tid, "<exit>")
            proc_to_ops[(pid, exid, tid)] = [exit_node]
            nodes.append(exit_node)
            return exit_node
        else:
            return proc_to_ops[(pid, exid, tid)][-1]

    fork_join_edges = list[tuple[Node, Node]]()
    exec_edges = list[tuple[Node, Node]]()

    # Hook up forks/joins
    for node in list(nodes):
        pid, exid, tid, op = node
        if False:
            pass
        elif isinstance(op, CloneOp):
            if op.flags & CLONE_THREAD:
                # Spawning a thread links to the current PID and exec epoch
                target = (pid, exid, op.child_thread_id)
            else:
                # New process always links to exec epoch 0 and main thread
                # THe TID of the main thread is the same as the PID
                target = (op.child_process_id, 0, op.child_process_id)
            exec_edges.append((node, first(*target)))
        elif isinstance(op, WaitOp) and op.ferrno == 0 and op.ret > 0:
            # Always wait for main thread of the last exec epoch
            if op.ferrno == 0:
                target = (op.ret, last_exec_epoch.get(op.ret, 0), op.ret)
                fork_join_edges.append((last(*target), node))
        elif isinstance(op, ExecOp):
            # Exec brings same pid, incremented exid, and main thread
            target = pid, exid + 1, 0
            fork_join_edges.append((node, first(*target)))

    # # Make the main thread exit at the same time as each thread
    for pid, process in process_tree_prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            for tid, thread in exec_epoch.threads.items():
                if tid != 0:
                    fork_join_edges.append((last(pid, exec_epoch_no, tid), last(pid, exec_epoch_no, pid)))

    def node_to_label(node: Node) -> str:
        inner_label = node[3] if isinstance(node[3], str) else node[3].__class__.__name__
        return f"{node[0]} {node[1]} {node[2]} {inner_label}"

    def node_to_id(node: Node) -> str:
        return f"\"node_{node[0]}_{node[1]}_{node[2]}_{id(node[3])}\""

    return "\n".join([
        "strict digraph {",
        *[
            f"  {node_to_id(node)} [label=\"{node_to_label(node)}\"];"
            for node in nodes
        ],
        *[
            f"  {node_to_id(node0)} -> {node_to_id(node1)} [color=\"green\"];"
            for node0, node1 in program_order_edges
        ],
        *[
            f"  {node_to_id(node0)} -> {node_to_id(node1)} [color=\"yellow\"];"
            for node0, node1 in exec_edges
        ],
        *[
            f"  {node_to_id(node0)} -> {node_to_id(node1)} [color=\"red\"];"
            for node0, node1 in fork_join_edges
        ],
        "}",
    ])
