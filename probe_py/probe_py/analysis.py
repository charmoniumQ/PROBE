import collections
import dataclasses
import enum
import os
import pathlib
import rich
import sys
import typing
import networkx
import numpy
from .ptypes import TaskType, Pid, ExecNo, Tid, ProbeLog, Inode, InodeVersion, initial_exec_no, Host, Device
from .ops import Op, CloneOp, ExecOp, WaitOp, OpenOp, CloseOp, InitExecEpochOp, InitThreadOp, StatOp
from .graph_utils import list_edges_from_start_node


class EdgeLabel(enum.IntEnum):
    PROGRAM_ORDER = 1
    FORK_JOIN = 2
    EXEC = 3

@dataclasses.dataclass(frozen=True)
class ProcessNode:
    pid: int
    cmd: tuple[str,...]


@dataclasses.dataclass(frozen=True)
class FileAccess:
    inode_version: InodeVersion
    path: pathlib.Path

    @property
    def label(self) -> str:
        return f"{self.path!s} inode {self.inode_version.inode}"


# type alias for a node
OpNode = tuple[Pid, ExecNo, Tid, int]

# type for the edges
EdgeType: typing.TypeAlias = tuple[OpNode, OpNode]


if typing.TYPE_CHECKING:
    HbGraph: typing.TypeAlias = networkx.DiGraph[OpNode]
    DfGraph: typing.TypeAlias = networkx.DiGraph[FileAccess | ProcessNode]
    ProcessTree: typing.TypeAlias = networkx.DiGraph[str]
else:
    HbGraph = networkx.DiGraph
    DfGraph = networkx.DiGraph
    ProcessTree = networkx.DiGraph


def probe_log_to_process_tree(probe_log: ProbeLog) -> ProcessTree:
    G = ProcessTree()

    def epoch_node_id(pid: int, epoch_no: int) -> str:
        return f"pid{pid}_epoch{epoch_no}"

    for pid, process in probe_log.processes.items():
        for epoch_no, epoch in process.execs.items():
            cmd_args = None

            for tid, thread in epoch.threads.items():
                for op in thread.ops:
                    op_data = op.data

                    if isinstance(op_data, ExecOp):
                        args_list = [arg.decode('utf-8') for arg in op_data.argv]
                        cmd_args = " ".join(args_list)
                        break
                if cmd_args:
                    break

            if cmd_args:
                label = f"PID={pid}\n {cmd_args}"
            else:
                label = f"PID={pid}\n cloned from parent"

            node_id = epoch_node_id(pid, epoch_no)
            G.add_node(node_id, label=label)

    for pid, process in probe_log.processes.items():
        for exec_epoch_no, exec_epoch in process.execs.items():
            parent_node_id = epoch_node_id(pid, exec_epoch_no)

            for tid, thread in exec_epoch.threads.items():
                for op in thread.ops:
                    op_data = op.data

                    if isinstance(op_data, CloneOp) and op_data.ferrno == 0:
                        child_pid = op_data.task_id
                        if child_pid in probe_log.processes:
                            child_epoch = 0
                            child_node_id = epoch_node_id(child_pid, child_epoch)

                            if G.has_node(child_node_id):
                                G.add_edge(parent_node_id, child_node_id, label="clone", constraint="true")

                    if isinstance(op_data, ExecOp):
                        new_epoch_no = exec_epoch_no + 1
                        new_node_id = epoch_node_id(pid, new_epoch_no)

                        if G.has_node(new_node_id):
                            G.add_edge(parent_node_id, new_node_id, label="exec", constraint="false")

    return G

def get_max_parallelism_latest(hb_graph: HbGraph, probe_log: ProbeLog) -> int:
    visited = set()
    # counter is set to 1 to include the main parent process
    counter = 1 
    max_counter = 1
    start_node = [node for node in hb_graph.nodes() if hb_graph.in_degree(node) == 0][0]
    queue = collections.deque[tuple[OpNode, OpNode | None]]([(start_node, None)])  # (current_node, parent_node)
    while queue:
        node, parent = queue.popleft()
        if node in visited:
            continue
        pid, exec_epoch_no, tid, op_index = node
        if(parent):
            parent_pid, parent_exec_epoch_no, parent_tid, parent_op_index = parent
            parent_op = get_op(probe_log, parent_pid, parent_exec_epoch_no, parent_tid, parent_op_index).data
        node_op = get_op(probe_log, pid, exec_epoch_no, tid, op_index).data

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
