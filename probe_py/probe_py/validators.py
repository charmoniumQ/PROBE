from typing import Iterator
from .ops import InitExecEpochOp, InitThreadOp, WaitOp, ExecOp, OpenOp, CloseOp, CloneOp
from .ptypes import Tid, Pid, ProbeLog, TaskType


"""The analyses make a lot of assumptions about the probe_log.

These assumptions seem reasonable and even guaranteed by the implementaiton of
libprobe, but we should still test them, for defensive coding and error-localization.

"""

def validate_probe_log(
        probe_log: ProbeLog,
) -> Iterator[str]:
    """Yields validation errors as strings

    If you are fixing errors, resolve the first one first. Programmers can
    assume the errors above the particular check have been checked and resolved.

    """
    yield from validate_root_pid(probe_log)
    yield from validate_init_ops(probe_log)
    yield from validate_exec_epoch_presence(probe_log)
    yield from validate_clone_targets(probe_log)
    yield from validate_clones_and_waits(probe_log)
    yield from validate_opens_and_closes(probe_log)


def validate_root_pid(
        probe_log: ProbeLog,
) -> Iterator[str]:
    n_roots = 0
    for pid, process in probe_log.processes.items():
        #first_op = process.execs[initial_exec_no].threads[pid.main_thread()].ops[0]
        for other_pid, other_process in probe_log.processes.items():
            raise NotImplementedError()
    if n_roots == 0:
        yield "No root pid found"
    elif n_roots > 1:
        yield "Multiple roots found"


def validate_init_ops(
        probe_log: ProbeLog,
) -> Iterator[str]:
    """Init ops have to appear before any other ops"""
    for pid, process in probe_log.processes.items():
        for exec_no, exec_ep in process.execs.items():
            for tid, thread in exec_ep.threads.items():
                op_idx = 0
                op = thread.ops[op_idx]
                if tid == pid.main_thread():
                    if not isinstance(op.data, InitExecEpochOp):
                        yield f"{pid}.{exec_no}.{tid}.{op_idx} should be InitExecEpochOp, not {op.data}"
                    op_idx += 1

                op = thread.ops[op_idx]
                if not isinstance(op.data, InitThreadOp):
                    yield f"{pid}.{exec_no}.{tid}.{op_idx} should be InitThreadOp, not {op.data}"
                op_idx += 1

                for op_no, op in enumerate(thread.ops[op_idx:]):
                    if isinstance(op, (InitExecEpochOp, InitThreadOp)):
                        yield f"{pid}.{exec_no}.{tid}.{op_no + op_idx} is Init*Op, but it does not appear early enough"


def validate_exec_epoch_presence(probe_log: ProbeLog) -> Iterator[str]:
    """We must have all exec_epochs from 0..N"""
    for pid, process in probe_log.processes.items():
        present_execs = set(process.execs.keys())
        max_exec_no = max(process.execs.keys())
        expected_execs = set(range(0, max_exec_no))
        if present_execs != expected_execs:
            yield f"{pid} has execs {sorted(present_execs)}; expected [0, ..., {max_exec_no}]"


def validate_clone_targets(probe_log: ProbeLog) -> Iterator[str]:
    """Clone must return threads that we observe"""
    pids = probe_log.processes.keys()
    for pid, process in probe_log.processes.items():
        for exec_no, exec_ep in process.execs.items():
            pthread_ids = {
                op.pthread_id
                for tid, thread in exec_ep.threads.items()
                for op in thread.ops
            }
            iso_c_thread_ids = {
                op.pthread_id
                for tid, thread in exec_ep.threads.items()
                for op in thread.ops
            }
            for tid, thread in exec_ep.threads.items():
                for op in thread.ops:
                    if isinstance(op.data, CloneOp) and op.data.ferrno == 0:
                        if op.data.task_type == TaskType.TASK_PID and Pid(op.data.task_id) not in pids:
                            yield f"CloneOp returned a PID {op.data.task_id} that we didn't track"
                        elif op.data.task_type == TaskType.TASK_TID and Tid(op.data.task_id) not in exec_ep.threads:
                            yield f"CloneOp returned a TID {op.data.task_id} that we didn't track"
                        elif op.data.task_type == TaskType.TASK_PTHREAD and op.data.task_id not in pthread_ids:
                            yield f"CloneOp returned a pthread ID {op.data.task_id} that we didn't track"
                        elif op.data.task_type == TaskType.TASK_ISO_C_THREAD and op.data.task_id not in iso_c_thread_ids:
                            yield f"CloneOp returned a ISO C Thread ID {op.data.task_id} that we didn't track"


def validate_clones_and_waits(probe_log: ProbeLog) -> Iterator[str]:
    """Cloned PIDs and TIDs == waited PIDs and TIDs"""
    cloned_processes = set[tuple[TaskType, int]]()
    waited_processes = set[tuple[TaskType, int]]()
    for pid, process in probe_log.processes.items():
        for exec_no, exec_ep in process.execs.items():
            for tid, thread in exec_ep.threads.items():
                for op in thread.ops:
                    if isinstance(op.data, WaitOp) and op.data.ferrno == 0:
                        # TODO: Replace TaskType(x) with x in this file, once Rust can emit enums
                        waited_processes.add((TaskType(op.data.task_type), op.data.task_id))
                    elif isinstance(op.data, CloneOp) and op.data.ferrno == 0:
                        cloned_processes.add((TaskType(op.data.task_type), op.data.task_id))
                        if op.data.task_type == TaskType.TASK_PID:
                            # New process implicitly also creates a new thread
                            cloned_processes.add((TaskType.TASK_TID, op.data.task_id))
    if waited_processes != cloned_processes:
        yield f"Waited different PIDs or TIDs than we cloned: {waited_processes=} {cloned_processes=}"


def validate_execs(probe_log: ProbeLog) -> Iterator[str]:
    for pid, process in probe_log.processes.items():
        for exec_no, exec_ep in process.execs.items():
            for tid, thread in exec_ep.threads.items():
                for op in thread.ops:
                    if isinstance(op.data, ExecOp):
                        if not op.data.argv:
                            yield "No arguments stored in exec syscall"


def validate_opens_and_closes(probe_log: ProbeLog) -> Iterator[str]:
    opened_fds = set[int]()
    closed_fds = set[int]()
    for pid, process in probe_log.processes.items():
        for exec_no, exec_ep in process.execs.items():
            for tid, thread in exec_ep.threads.items():
                for op in thread.ops:
                    if isinstance(op.data, OpenOp) and op.data.ferrno == 0:
                        opened_fds.add(op.data.fd)
                    elif isinstance(op.data, CloseOp) and op.data.ferrno == 0:
                        # Range in Python is up-to-not-including high_fd, so we add one to it.
                        closed_fds.update(range(op.data.low_fd, op.data.high_fd + 1))
    reserved_fds = {0, 1, 2}
    opened_fds -= reserved_fds
    closed_fds -= reserved_fds
    if opened_fds != closed_fds:
        yield f"Opened different fds than we closed {opened_fds=} {closed_fds=}"
