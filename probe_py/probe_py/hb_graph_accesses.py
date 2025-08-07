import collections
import dataclasses
import enum
import os
import pathlib
import warnings
import networkx
import tqdm
from . import hb_graph
from . import ops
from . import ptypes


class AccessMode(enum.IntEnum):
    """In what way are we accessing the inode version?"""
    EXEC = enum.auto()
    DLOPEN = enum.auto()
    READ = enum.auto()
    WRITE = enum.auto()
    READ_WRITE = enum.auto()
    TRUNCATE_WRITE = enum.auto()

    def is_side_effect_free(self) -> bool:
        return self in {AccessMode.EXEC, AccessMode.DLOPEN, AccessMode.READ}

    @staticmethod
    def from_open_flags(flags: int) -> AccessMode:
        access_mode = flags & os.O_ACCMODE
        if access_mode == os.O_RDONLY:
            return AccessMode.READ
        elif flags & (os.O_TRUNC | os.O_CREAT):
            return AccessMode.TRUNCATE_WRITE
        elif access_mode == os.O_WRONLY:
            return AccessMode.WRITE
        elif access_mode == os.O_RDWR:
            return AccessMode.READ_WRITE
        else:
            raise ptypes.InvalidProbeLog(f"Invalid open flags: 0x{flags:x}")


class Phase(enum.StrEnum):
    BEGIN = enum.auto()
    END = enum.auto()


@dataclasses.dataclass
class Access:
    phase: Phase
    mode: AccessMode
    inode: ptypes.Inode
    path: pathlib.Path
    op_node: hb_graph.OpNode
    fd: int | None


def hb_graph_to_accesses(
        probe_log: ptypes.ProbeLog,
        hbg: hb_graph.HbGraph,
) -> collections.abc.Iterator[Access | hb_graph.OpNode]:
    """Reduces a happens-before graph to an ordered list of accesses in one possible schedule."""

    @dataclasses.dataclass
    class FileDescriptor2:
        mode: AccessMode
        inode: ptypes.Inode
        path: pathlib.Path
        cloexec: bool

    proc_fd_to_fd = collections.defaultdict[ptypes.Pid, dict[int, FileDescriptor2]](dict)

    def close(fd: int, node: hb_graph.OpNode) -> collections.abc.Iterator[Access]:
        if file_desc := proc_fd_to_fd[node.pid].get(fd):
            file_desc = proc_fd_to_fd[node.pid][fd]
            yield Access(Phase.END, file_desc.mode, file_desc.inode, file_desc.path, node, fd)
            del proc_fd_to_fd[node.pid][fd]
        else:
            warnings.warn(f"Process {node.pid} successfully closed an FD {fd} we never traced. This could come from pipe or pipe2.")

    def openfd(
            fd: int,
            mode: AccessMode,
            cloexec: bool,
            node: hb_graph.OpNode,
            path: ops.Path,
    ) -> collections.abc.Iterator[Access]:
        inode = ptypes.InodeVersion.from_probe_path(path).inode
        if fd in proc_fd_to_fd[node.pid]:
            warnings.warn(f"Process {node.pid} closed FD {fd} without our knowledge.")
            yield from close(fd, node)
        parsed_path = pathlib.Path(path.path.decode())
        proc_fd_to_fd[node.pid][fd] = FileDescriptor2(mode, inode, parsed_path, cloexec)
        yield Access(Phase.BEGIN, mode, inode, parsed_path, node, fd)

    interesting_op_types = (ops.OpenOp, ops.CloseOp, ops.DupOp, ops.ExecOp, ops.SpawnOp, ops.InitExecEpochOp, ops.CloneOp)
    reduced_hb_graph = hb_graph.retain_only(
        probe_log,
        hbg,
        lambda node, op: isinstance(op.data, interesting_op_types) and getattr(op.data, "ferrno", 0) == 0,
    )

    root_pid = probe_log.get_root_pid()
    for node in tqdm.tqdm(
            networkx.topological_sort(reduced_hb_graph),
            total=len(reduced_hb_graph),
            desc="Finding DFG",
    ):
        yield node
        op_data = probe_log.get_op(*node.op_quad()).data
        match op_data:
            case ops.InitExecEpochOp():
                if node.pid == root_pid:
                    yield from openfd(0, AccessMode.READ, False, node, op_data.stdin)
                    yield from openfd(1, AccessMode.TRUNCATE_WRITE, False, node, op_data.stdout)
                    yield from openfd(2, AccessMode.TRUNCATE_WRITE, False, node, op_data.stderr)
            case ops.OpenOp():
                mode = AccessMode.from_open_flags(op_data.flags)
                cloexec = bool(op_data.flags & os.O_CLOEXEC)
                yield from openfd(op_data.fd, mode, cloexec, node, op_data.path)
            case ops.ExecOp():
                for fd, file_desc in list(proc_fd_to_fd[node.pid].items()):
                    if file_desc.cloexec:
                        yield from close(fd, node)
                exe_inode = ptypes.InodeVersion.from_probe_path(op_data.path).inode
                exe_path = pathlib.Path(op_data.path.path.decode())
                yield Access(Phase.BEGIN, AccessMode.EXEC, exe_inode, exe_path, node, None)
                yield Access(Phase.END, AccessMode.EXEC, exe_inode, exe_path, node, None)
            case ops.CloseOp():
                yield from close(op_data.fd, node)
            case ops.DupOp():
                if old_file_desc := proc_fd_to_fd[node.pid].get(op_data.old):
                    # dup2 and dup3 close the new FD, if it was open
                    if op_data.new in list(proc_fd_to_fd[node.pid]):
                        yield from close(op_data.new, node)
                    proc_fd_to_fd[node.pid][op_data.new] = old_file_desc
                else:
                    warnings.warn(f"Process {node.pid} successfully closed an FD {op_data.old} we never traced. This could come from pipe or pipe2.")
            case ops.CloneOp():
                if op_data.task_type == ptypes.TaskType.TASK_PID and not (op_data.flags & os.CLONE_THREAD):
                    target = ptypes.Pid(op_data.task_id)
                    if op_data.flags & os.CLONE_FILES:
                        proc_fd_to_fd[target] = proc_fd_to_fd[node.pid]
                    else:
                        proc_fd_to_fd[target] = {**proc_fd_to_fd[node.pid]}
        is_last_op_in_process = not any(
            successor.pid == node.pid
            for successor in reduced_hb_graph.successors(node)
        )
        if is_last_op_in_process:
            for fd in list(proc_fd_to_fd[node.pid].keys()):
                yield from close(fd, node)

    assert not proc_fd_to_fd, "somehow we still have open file descriptors at the end."


def verify_access_list(
        accesses_and_nodes: list[Access | hb_graph.OpNode]
) -> None:
    pass
