import collections
from .ops import CloneOp, WaitOp
from . import ptypes


def get_max_parallelism_latest(hb_graph: ptypes.HbGraph, probe_log: ptypes.ProbeLog) -> int:
    visited = set()
    # counter is set to 1 to include the main parent process
    counter = 1 
    max_counter = 1
    start_node = [node for node in hb_graph.nodes() if hb_graph.in_degree(node) == 0][0]
    queue = collections.deque[tuple[ptypes.OpQuad, ptypes.OpQuad | None]]([(start_node, None)])  # (current_node, parent_node)
    while queue:
        node, parent = queue.popleft()
        if node in visited:
            continue
        if parent:
            parent_op = probe_log.get_op(parent).data
        node_op = probe_log.get_op(node).data

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
