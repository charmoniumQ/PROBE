from __future__ import annotations
import pathlib
from . import ops
import os
from dataclasses import dataclass
import enum
import typing


@dataclass(frozen=True)
class ThreadProvLog:
    tid: int
    ops: typing.Sequence[ops.Op]

@dataclass(frozen=True)
class ExecEpochProvLog:
    epoch: int
    threads: typing.Mapping[int, ThreadProvLog]


@dataclass(frozen=True)
class ProcessProvLog:
    pid: int
    exec_epochs: typing.Mapping[int, ExecEpochProvLog]


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class ProvLog:
    processes: typing.Mapping[int, ProcessProvLog]
    inodes: typing.Mapping[InodeVersionLog, pathlib.Path]
    has_inodes: bool

# TODO: implement this in probe_py.generated.ops
class TaskType(enum.IntEnum):
    TASK_PID = 0
    TASK_TID = 1
    TASK_ISO_C_THREAD = 2
    TASK_PTHREAD = 3
