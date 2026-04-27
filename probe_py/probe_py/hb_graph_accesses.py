import collections
import dataclasses
import os
import pathlib
import warnings
from . import graph_utils
from . import headers as ops
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

    proc_fd_to_fd = collections.defaultdict[ptypes.Pid, dict[ops.OpenNumber, FileDescriptor2]](dict)

    def close(open_number: ops.OpenNumber, node: ptypes.OpQuad) -> collections.abc.Iterator[ptypes.Access]:
        if file_desc := proc_fd_to_fd[node.pid].get(open_number):
            file_desc = proc_fd_to_fd[node.pid][open_number]
            yield ptypes.Access(ptypes.Phase.END, file_desc.mode, file_desc.inode, file_desc.path, node, open_number)
            del proc_fd_to_fd[node.pid][open_number]
        else:
            warnings.warn(ptypes.UnusualProbeLog(
                f"{node} successfully closed an ON {open_number} we never traced.",
            ))

    def openfd(
            mode: ptypes.AccessMode,
            cloexec: bool,
            node: ptypes.OpQuad,
            inode: ops.Inode,
            path_arg: ops.PathArg,
            open_number: ops.OpenNumber,
    ) -> collections.abc.Iterator[ptypes.Access]:
        if open_number in proc_fd_to_fd[node.pid]:
            warnings.warn(ptypes.UnusualProbeLog(
                f"ON {open_number} closed was without our knowledge before {node}.",
            ))
            yield from close(open_number, node)
        path = proc_fd_to_fd[node.pid][path_arg.directory].path / (path_arg.name or b"").decode()
        inode2 = ptypes.Inode.from_ops_inode(inode)
        proc_fd_to_fd[node.pid][open_number] = FileDescriptor2(mode, inode2, path, cloexec)
        yield ptypes.Access(ptypes.Phase.BEGIN, mode, inode2, path, node, open_number)

    for node in graph_utils.topological_sort_depth_first(
            hbg,
            score_children=lambda parent, child: 0 if parent.pid == child.pid else 1 if parent.pid < child.pid else 2,
    ):
        assert node
        yield node
        op = probe_log.get_op(node)
        op_data = op.data
        match op_data:
            case ops.Open():
                if op.ferrno == 0:
                    mode = ptypes.AccessMode.from_open_flags(op_data.flags)
                    cloexec = bool(op_data.flags & os.O_CLOEXEC)
                    yield from openfd(mode, cloexec, node, op_data.inode, op_data.path, op_data.open_number)
            case ops.Exec():
                if op.ferrno == 0:
                    for on, file_desc in list(proc_fd_to_fd[node.pid].items()):
                        if file_desc.cloexec:
                            yield from close(on, node)
                    exe_inode = ptypes.Inode.from_ops_inode(op_data.inode)
                    path = proc_fd_to_fd[node.pid][op_data.path.directory].path / (op_data.path.name or b"").decode()
                    yield ptypes.Access(ptypes.Phase.BEGIN, ptypes.AccessMode.EXEC, exe_inode, path, node, None)
                    yield ptypes.Access(ptypes.Phase.END, ptypes.AccessMode.EXEC, exe_inode, path, node, None)
            case ops.Close():
                if op.ferrno == 0:
                    yield from close(op_data.open_number, node)
            case ops.Clone():
                if op.ferrno == 0 and op_data.task_type == ops.TaskType.PID and not (op_data.flags & os.CLONE_THREAD):
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
            for on in list(proc_fd_to_fd[node.pid].keys()):
                yield from close(on, node)

    for pid, fd_table in proc_fd_to_fd.items():
        assert not fd_table, f"somehow we still have open file descriptors at the end. {pid} {fd_table}"
