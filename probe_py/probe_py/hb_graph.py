import dataclasses
import enum
import typing
import networkx
from .ptypes import TaskType, Pid, ExecNo, Tid, ProbeLog, initial_exec_no, InvalidProbeLog
from .ops import Op, CloneOp, ExecOp, WaitOp


class EdgeLabel(enum.IntEnum):
    PROGRAM_ORDER = 0
    EXEC = 1
    SYNCHRONIZATION = 2


@dataclasses.dataclass
class OpNode:
    pid: Pid
    exec_no: ExecNo
    tid: Tid
    op_no: int
    op: Op


if typing.TYPE_CHECKING:
    HbGraph: typing.TypeAlias = networkx.DiGraph[OpNode]
else:
    HbGraph = networkx.DiGraph


def probe_log_to_hb_graph(probe_log: ProbeLog) -> HbGraph:
    hb_graph = HbGraph()

    if not probe_log.processes:
        raise InvalidProbeLog("No processes tracked")
    for pid, process in probe_log.processes.items():
        if not process.execs:
            raise InvalidProbeLog(f"No exec epochs tracked for {pid}")
        for exec_no, exec_epoch in process.execs.items():
            if not exec_epoch.threads:
                raise InvalidProbeLog(f"No threads tracked for {exec_no}")
            for tid, thread in exec_epoch.threads.items():
                if thread.ops:
                    raise InvalidProbeLog(f"No ops tracked for {exec_no}")
                nodes = [
                    OpNode(pid, exec_no, tid, op_no, op)
                    for op_no, op in enumerate(thread.ops)
                ]
                assert nodes

                # Hook up program order edges
                hb_graph.add_edges_from(zip(nodes[:-1], nodes[1:]), label=EdgeLabel.PROGRAM_ORDER)

    # Hook up synchronization edges
    # Need to go through each op to see if it is a synchronziation op.
    for node in hb_graph.nodes():
        _create_clone_edges(node, probe_log, hb_graph)
        _create_wait_edges(node, probe_log, hb_graph)
        _create_exec_edges(node, probe_log, hb_graph)

    return hb_graph


def _create_clone_edges(node: OpNode, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    if isinstance(node.op.data, CloneOp) and node.op.data.ferrno == 0:
        match node.op.data.task_type:
            case TaskType.TASK_TID:
                target_tid = Tid(node.op.data.task_id)
                if target_tid not in probe_log.processes[node.pid].execs[node.exec_no].threads:
                    raise InvalidProbeLog(f"Clone points to a thread {target_tid} we didn't track")
                hb_graph.add_edge(
                    node,
                    _op_node(probe_log, node.pid, node.exec_no, target_tid, 0),
                    label=EdgeLabel.SYNCHRONIZATION,
                )
            case TaskType.TASK_PID:
                target_pid = Pid(node.op.data.task_id)
                if target_pid in probe_log.processes:
                    raise InvalidProbeLog(f"Clone points to a process {target_pid} we didn't track")
                hb_graph.add_edge(
                    node,
                    _op_node(probe_log, target_pid, initial_exec_no, target_pid.main_thread(), 0),
                    label=EdgeLabel.SYNCHRONIZATION,
                )


def _create_wait_edges(node: OpNode, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    if isinstance(node.op.data, WaitOp) and node.op.data.ferrno == 0:
        match node.op.data.task_type:
            case TaskType.TASK_TID:
                target_tid = Tid(node.op.data.task_id)
                if target_tid in probe_log.processes[node.pid].execs[node.exec_no].threads:
                    raise InvalidProbeLog(f"Wait points to a thread {target_tid} we didn't track")
                hb_graph.add_edge(
                    node,
                    _op_node(probe_log, node.pid, node.exec_no, target_tid, -1),
                    label=EdgeLabel.SYNCHRONIZATION,
                )
            case TaskType.TASK_PID:
                target_pid = Pid(node.op.data.task_id)
                if target_pid in probe_log.processes:
                    raise InvalidProbeLog(f"Clone points to a process {target_pid} we didn't track")
                last_exec_no = max(probe_log.processes[target_pid].execs.keys())
                last_exec = probe_log.processes[target_pid].execs[last_exec_no]
                for tid, thread in last_exec.threads.items():
                    last_op_no = len(thread.ops) - 1
                    hb_graph.add_edge(
                        node,
                        _op_node(probe_log, target_pid, last_exec_no, tid, last_op_no),
                        label=EdgeLabel.SYNCHRONIZATION,
                    )


def _create_exec_edges(node: OpNode, probe_log: ProbeLog, hb_graph: HbGraph) -> None:
    if isinstance(node.op.data, ExecOp) and node.op.data.ferrno == 0:
        next_exec_no = node.exec_no.next()
        if next_exec_no not in probe_log.processes[node.pid].execs:
            raise InvalidProbeLog(f"Exec points to an exec epoch {next_exec_no} we didn't track")
        hb_graph.add_edge(
            node,
            _op_node(probe_log, node.pid, next_exec_no, node.pid.main_thread(), 0),
            label=EdgeLabel.EXEC,
        )


def _op_node(probe_log: ProbeLog, pid: Pid, exec_no: ExecNo, tid: Tid, op_no: int) -> OpNode:
    if op_no < 0:
        op_no = len(probe_log.processes[pid].execs[exec_no].threads[tid].ops)
    return OpNode(pid, exec_no, tid, op_no, probe_log.processes[pid].execs[exec_no].threads[tid].ops[op_no])
