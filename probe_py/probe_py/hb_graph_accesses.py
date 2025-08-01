import collections
import dataclasses
import os
import pathlib
import warnings
import networkx
import tqdm
from . import ops
from . import ptypes


def hb_graph_to_accesses(
        probe_log: ptypes.ProbeLog,
        hbg: ptypes.HbGraph,
) -> collections.abc.Iterator[ptypes.Access | ptypes.OpQuad]:
    """Reduces a happens-before graph to an ordered list of accesses in one possible schedule."""

    @dataclasses.dataclass
    class FileDescriptor2:
        mode: ptypes.AccessMode
        inode: ptypes.Inode
        path: pathlib.Path
        cloexec: bool

    proc_fd_to_fd = collections.defaultdict[ptypes.Pid, dict[int, FileDescriptor2]](dict)

    def close(fd: int, node: ptypes.OpQuad) -> collections.abc.Iterator[ptypes.Access]:
        if file_desc := proc_fd_to_fd[node.pid].get(fd):
            file_desc = proc_fd_to_fd[node.pid][fd]
            yield ptypes.Access(ptypes.Phase.END, file_desc.mode, file_desc.inode, file_desc.path, node, fd)
            del proc_fd_to_fd[node.pid][fd]
        else:
            warnings.warn(f"Process {node.pid} successfully closed an FD {fd} we never traced.")

    def openfd(
            fd: int,
            mode: ptypes.AccessMode,
            cloexec: bool,
            node: ptypes.OpQuad,
            path: ops.Path,
    ) -> collections.abc.Iterator[ptypes.Access]:
        inode = ptypes.InodeVersion.from_probe_path(path).inode
        if fd in proc_fd_to_fd[node.pid]:
            warnings.warn(f"Process {node.pid} closed FD {fd} without our knowledge.")
            yield from close(fd, node)
        parsed_path = pathlib.Path(path.path.decode())
        proc_fd_to_fd[node.pid][fd] = FileDescriptor2(mode, inode, parsed_path, cloexec)
        yield ptypes.Access(ptypes.Phase.BEGIN, mode, inode, parsed_path, node, fd)

    root_pid = probe_log.get_root_pid()
    for node in tqdm.tqdm(
            networkx.topological_sort(hbg),
            total=len(hbg),
            desc="Finding accesses",
    ):
        yield node
        op_data = probe_log.get_op(node).data
        match op_data:
            case ops.InitExecEpochOp():
                if node.exec_no == ptypes.initial_exec_no and node.pid == root_pid:
                    yield from openfd(0, ptypes.AccessMode.READ, False, node, op_data.stdin)
                    yield from openfd(1, ptypes.AccessMode.TRUNCATE_WRITE, False, node, op_data.stdout)
                    yield from openfd(2, ptypes.AccessMode.TRUNCATE_WRITE, False, node, op_data.stderr)
            case ops.OpenOp():
                mode = ptypes.AccessMode.from_open_flags(op_data.flags)
                cloexec = bool(op_data.flags & os.O_CLOEXEC)
                yield from openfd(op_data.fd, mode, cloexec, node, op_data.path)
            case ops.ExecOp():
                for fd, file_desc in list(proc_fd_to_fd[node.pid].items()):
                    if file_desc.cloexec:
                        yield from close(fd, node)
                exe_inode = ptypes.InodeVersion.from_probe_path(op_data.path).inode
                exe_path = pathlib.Path(op_data.path.path.decode())
                yield ptypes.Access(ptypes.Phase.BEGIN, ptypes.AccessMode.EXEC, exe_inode, exe_path, node, None)
                yield ptypes.Access(ptypes.Phase.END, ptypes.AccessMode.EXEC, exe_inode, exe_path, node, None)
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
            for successor in hbg.successors(node)
        )
        if is_last_op_in_process:
            for fd in list(proc_fd_to_fd[node.pid].keys()):
                yield from close(fd, node)

    for pid, fd_table in proc_fd_to_fd.items():
        assert not fd_table, f"somehow we still have open file descriptors at the end. {pid} {fd_table}"
