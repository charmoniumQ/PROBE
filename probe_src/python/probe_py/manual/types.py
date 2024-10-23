from __future__ import annotations
import pathlib
from ..generated import ops
import dataclasses
import enum
import typing


# New types encourage type saftey,
# E.g., not supplying a pid where we require a tid
class Pid(int):
    def main_thread(self) -> Tid:
        """Returns the Tid of the main thread associated with this pid."""
        return Tid(self)


class ExecNo(int):
    pass


initial_exec_no = ExecNo(0)


class Tid(int):
    pass


@dataclasses.dataclass(frozen=True)
class Host:
    host_name: str
    uniquifier: int


@dataclasses.dataclass(frozen=True)
class Inode:
    host: Host
    device_major: int
    device_minor: int
    inode: int


@dataclasses.dataclass(frozen=True)
class InodeVersion:
    inode: Inode
    mtime_sec: int
    mtime_nsec: int
    size: int


@dataclasses.dataclass(frozen=True)
class ProbeOptions:
    copy_files: bool


@dataclasses.dataclass(frozen=True)
class ProbeLog:
    processes: typing.Mapping[Pid, typing.Mapping[ExecNo, typing.Tid, typing.Sequence[ops.Op]]]
    copied_files: typing.Mapping[InodeVersion, pathlib.Path]
    probe_options: ProbeOptions

    def ops(self) -> typing.Iterator[tuple[Pid, ExecNo, Tid, int, ops.Op]]:
        for pid, execs in self.processes.items():
            for exec_no, tids in execs.items():
                for tid, op_list in tids.items():
                    for op_no, op in enumerate(op_list):
                        yield pid, exec_no, tid, op_no, op


# TODO: implement this in probe_py.generated.ops
class TaskType(enum.IntEnum):
    TASK_PID = 0
    TASK_TID = 1
    TASK_ISO_C_THREAD = 2
    TASK_PTHREAD = 3
