import typing
from .headers import InitExecEpoch, InitThread, Wait, Exec, Clone, ExitThread, ExitProcess, TaskType
from .ptypes import Tid, Pid, ProbeLog


"""The analyses make a lot of assumptions about the probe_log.

These assumptions seem reasonable and even guaranteed by the implementation of
libprobe, but we should still test them, for defensive coding and error-localization.

"""

def validate_probe_log(
        probe_log: ProbeLog,
) -> typing.Iterator[str]:
    """Yields validation errors as strings

    If you are fixing errors, resolve the first one first. Programmers can
    assume the errors above the particular check have been checked and resolved.

    """
    yield from validate_init_ops(probe_log)
    yield from validate_exec_epoch_presence(probe_log)
    yield from validate_clone_targets(probe_log)
    yield from validate_clones_and_waits(probe_log)


def validate_init_ops(
        probe_log: ProbeLog,
) -> typing.Iterator[str]:
    """Init ops have to appear before any other ops"""
    for pid, process in probe_log.processes.items():
        for exec_no, exec_ep in process.execs.items():
            for tid, thread in exec_ep.threads.items():
                last_op_no = len(thread.ops) - 1
                op_idx = 0
                op = thread.ops[op_idx]
                if tid == pid.main_thread():
                    if not isinstance(op.data, InitExecEpoch):
                        yield f"{pid}.{exec_no}.{tid}.{op_idx} should be InitExecEpoch, not {op.data}"
                    op_idx += 1

                op = thread.ops[op_idx]
                if not isinstance(op.data, InitThread):
                    yield f"{pid}.{exec_no}.{tid}.{op_idx} should be InitThread, not {op.data}"
                op_idx += 1

                for op_no, op in enumerate(thread.ops[op_idx:]):
                    if isinstance(op, (InitExecEpoch, InitThread)):
                        yield f"{pid}.{exec_no}.{tid}.{op_no + op_idx} is Init*Op, but it does not appear early enough"
                    elif isinstance(op, (ExitThread, ExitProcess)) and op_no != last_op_no:
                        yield f"{pid}.{exec_no}.{tid}.{op_no + op_idx} is ExitThread, but it does not appear last"


def validate_exec_epoch_presence(probe_log: ProbeLog) -> typing.Iterator[str]:
    """We must have all exec_epochs from 0..N"""
    for pid, process in probe_log.processes.items():
        present_execs = set(process.execs.keys())
        max_exec_no = max(process.execs.keys())
        expected_execs = set(range(0, max_exec_no + 1))
        if present_execs != expected_execs:
            yield f"{pid} has execs {sorted(present_execs)}; expected [0, ..., {max_exec_no}]"


def validate_clone_targets(probe_log: ProbeLog) -> typing.Iterator[str]:
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
                    if isinstance(op.data, Clone) and op.ferrno == 0:
                        if op.data.task_type == TaskType.PID and Pid(op.data.task_id) not in pids:
                            yield f"Clone returned a PID {op.data.task_id} that we didn't track"
                        elif op.data.task_type == TaskType.TID and Tid(op.data.task_id) not in exec_ep.threads:
                            yield f"Clone returned a TID {op.data.task_id} that we didn't track"
                        elif op.data.task_type == TaskType.PTHREAD and op.data.task_id not in pthread_ids:
                            yield f"Clone returned a pthread ID {op.data.task_id} that we didn't track"
                        elif op.data.task_type == TaskType.ISO_C_THREAD and op.data.task_id not in iso_c_thread_ids:
                            yield f"Clone returned a ISO C Thread ID {op.data.task_id} that we didn't track"


def validate_clones_and_waits(probe_log: ProbeLog) -> typing.Iterator[str]:
    """Cloned PIDs and TIDs == waited PIDs and TIDs"""
    cloned_processes = set[tuple[TaskType, int]]()
    waited_processes = set[tuple[TaskType, int]]()
    for pid, process in probe_log.processes.items():
        for exec_no, exec_ep in process.execs.items():
            for tid, thread in exec_ep.threads.items():
                for op in thread.ops:
                    if isinstance(op.data, Wait) and op.ferrno == 0:
                        # TODO: Replace TaskType(x) with x in this file, once Rust can emit enums
                        waited_processes.add((TaskType(op.data.task_type), op.data.task_id))
                    elif isinstance(op.data, Clone) and op.ferrno == 0:
                        cloned_processes.add((TaskType(op.data.task_type), op.data.task_id))
                        if op.data.task_type == TaskType.PID:
                            # New process implicitly also creates a new thread
                            cloned_processes.add((TaskType.TID, op.data.task_id))
    if waited_processes != cloned_processes:
        yield f"Waited different PIDs or TIDs than we cloned: {waited_processes=} {cloned_processes=}"


def validate_execs(probe_log: ProbeLog) -> typing.Iterator[str]:
    for pid, process in probe_log.processes.items():
        for exec_no, exec_ep in process.execs.items():
            for tid, thread in exec_ep.threads.items():
                for op in thread.ops:
                    if isinstance(op.data, Exec):
                        if not op.data.argv:
                            yield "No arguments stored in exec syscall"
