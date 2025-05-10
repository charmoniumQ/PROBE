import typing
import networkx
from . import hb_graph
from . import ptypes
from . import ops


if typing.TYPE_CHECKING:
    ExecProcessTree: typing.TypeAlias = networkx.DiGraph[tuple[ptypes.Pid, ptypes.ExecNo]]
    ProcessTree: typing.TypeAlias = networkx.DiGraph[ptypes.Pid]
else:
    ExecProcessTree = networkx.DiGraph
    ProcessTree = networkx.DiGraph


def hb_graph_to_exec_process_tree(
        probe_log: ptypes.ProbeLog,
        hbg: hb_graph.HbGraph,
) -> ExecProcessTree:
    exec_process_tree = ExecProcessTree()

    for node in networkx.dfs_preorder_nodes(hbg):
        op = probe_log.get_op(*node.op_quad())
        if isinstance(op.data, ops.ExecOp) and op.data.ferrno == 0:
            exec_process_tree.add_edge(
                (node.pid, node.exec_no),
                (node.pid, node.exec_no.next()),
            )
        elif isinstance(op.data, ops.CloneOp) and op.data.ferrno == 0 and op.data.task_type == ptypes.TaskType.TASK_PID:
            exec_process_tree.add_edge(
                (node.pid, node.exec_no),
                (ptypes.Pid(op.data.task_id), ptypes.initial_exec_no),
            )

    return exec_process_tree


def hb_graph_to_process_tree(
        probe_log: ptypes.ProbeLog,
        hbg: hb_graph.HbGraph,
) -> ProcessTree:
    process_tree = ProcessTree()

    for node in networkx.dfs_preorder_nodes(hbg):
        op = probe_log.get_op(*node.op_quad())
        if isinstance(op.data, ops.CloneOp) and op.data.ferrno == 0 and op.data.task_type == ptypes.TaskType.TASK_PID:
            process_tree.add_edge(
                node.pid,
                ptypes.Pid(op.data.task_id),
            )

    return process_tree
