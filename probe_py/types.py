from __future__ import annotations
import pathlib
import functools
import socket
import random
import datetime
from . import ops
from . import consts
import os
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

    @functools.cache
    @staticmethod
    def localhost() -> Host:
        """Returns a Host object representing the current host"""
        node_name = consts.PROBE_HOME / "node_name"
        if node_name.exists():
            return Host(socket.gethostname(), int(node_name.read_text(), 16))
        else:
            hostname = socket.gethostname()
            rng = random.Random(int(datetime.datetime.now().timestamp()) ^ hash(hostname))
            bits_per_hex_digit = 4
            hex_digits = 8
            random_number = rng.getrandbits(bits_per_hex_digit * hex_digits)
            node_name = f"{random_number:0{hex_digits}x}.{hostname}"
            node_name.write_text(node_name)
            return Host(hostname, random_number)


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

    @staticmethod
    def from_path(path: pathlib.Path) -> InodeVersion:
        s = path.stat()
        return InodeVersion(
            Inode(
                Host.localhost(),
                os.major(s.st_dev),
                os.minor(s.st_dev),
                s.st_ino,
            ),
            s.st_mtime_ns // int(1e9),
            s.st_mtime_ns %  int(1e9),
            s.st_size,
        )


@dataclasses.dataclass(frozen=True)
class ProbeOptions:
    copy_files: bool


@dataclasses.dataclass(frozen=True)
class Thread:
    tid: Tid
    ops: typing.Sequence[ops.Op]


@dataclasses.dataclass(frozen=True)
class Exec:
    exec_no: ExecNo
    threads: typing.Mapping[Tid, Thread]


@dataclasses.dataclass(frozen=True)
class Process:
    pid: Pid
    execs: typing.Mapping[ExecNo, Exec]


@dataclasses.dataclass(frozen=True)
class ProbeLog:
    processes: typing.Mapping[Pid, Process]
    copied_files: typing.Mapping[InodeVersion, pathlib.Path]
    probe_options: ProbeOptions
    host: Host


# TODO: implement this in probe_py.generated.ops
class TaskType(enum.IntEnum):
    TASK_PID = 0
    TASK_TID = 1
    TASK_ISO_C_THREAD = 2
    TASK_PTHREAD = 3
