from __future__ import annotations
import pathlib
from . import ops
import os
import dataclasses
import enum
import typing



@dataclasses.dataclass(frozen=True)
class ProbeOptions:
    copy_files: bool


@dataclasses.dataclass(frozen=True)
class InodeVersionLog:
    device_major: int
    device_minor: int
    inode: int
    tv_sec: int
    tv_nsec: int
    size: int

    @staticmethod
    def from_path(path: pathlib.Path) -> InodeVersionLog:
        s = path.stat()
        return InodeVersionLog(
            os.major(s.st_dev),
            os.minor(s.st_dev),
            s.st_ino,
            s.st_mtime_ns // int(1e9),
            s.st_mtime_ns %  int(1e9),
            s.st_size,
        )

Tid: typing.TypeAlias = int
Pid: typing.TypeAlias = int
ExecNo: typing.TypeAlias = int


@dataclasses.dataclass(frozen=True)
class KernelThread:
    tid: Tid
    ops: typing.Sequence[ops.Op]


@dataclasses.dataclass(frozen=True)
class Exec:
    exec_no: ExecNo
    threads: typing.Mapping[Tid, KernelThread]


@dataclasses.dataclass(frozen=True)
class Process:
    pid: Pid
    execs: typing.Mapping[ExecNo, Exec]


@dataclasses.dataclass(frozen=True)
class ProbeLog:
    processes: typing.Mapping[Pid, Process]
    inodes: typing.Mapping[InodeVersionLog, pathlib.Path] | None
    has_inodes: bool

# TODO: implement this in probe_py.generated.ops
class TaskType(enum.IntEnum):
    TASK_PID = 0
    TASK_TID = 1
    TASK_ISO_C_THREAD = 2
    TASK_PTHREAD = 3
