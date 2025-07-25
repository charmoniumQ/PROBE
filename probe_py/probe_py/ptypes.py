from __future__ import annotations
import dataclasses
import enum
import hmac
import functools
import os
import pathlib
import random
import socket
import typing
import numpy
from . import ops
from . import consts


# New types encourage type saftey,
# E.g., not supplying a pid where we require a tid
class Pid(int):
    def main_thread(self) -> Tid:
        """Returns the Tid of the main thread associated with this pid."""
        return Tid(self)


class ExecNo(int):
    def prev(self) -> ExecNo:
        if self != 0:
            return ExecNo(self - 1)
        else:
            raise RuntimeError()
    def next(self) -> ExecNo:
        return ExecNo(self + 1)


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

        # https://www.freedesktop.org/software/systemd/man/latest/machine-id.html
        # This ID uniquely identifies the host. It should be considered "confidential".
        # If a stable unique identifier that is tied to the machine is needed for some application,
        # the machine ID should be hashed with a cryptographic, keyed hash function, using a fixed, application-specific key.
        if consts.SYSTEMD_MACHINE_ID.exists():
            machine_id_bytes = int(consts.SYSTEMD_MACHINE_ID.read_text().strip(), 16).to_bytes(16)
            hashed_machine_id = int.from_bytes(hmac.new(consts.APPLICATION_KEY, machine_id_bytes, "sha256").digest()) & ((1 << 64) - 1)
            return Host(socket.gethostname(), hashed_machine_id)
        else:
            # In containers and GitHub CI, SystemD machine-id may not exist.
            # Our alternative is to create a random iD, and store it in a persistent location
            alternative_machine_id = consts.get_state_dir() / "machine-id"
            if alternative_machine_id.exists():
                return Host(socket.gethostname(), int(alternative_machine_id.read_text(), 16))
            else:
                alternative_machine_id.parent.mkdir(exist_ok=True, parents=True)
                machine_id = int.from_bytes(random.randbytes(8))
                alternative_machine_id.write_text(f"{machine_id:08x}")
                return Host(socket.gethostname(), machine_id)


@dataclasses.dataclass(frozen=True)
class Device:
    major_id: int
    minor_id: int


@dataclasses.dataclass(frozen=True)
class Inode:
    host: Host
    device: Device
    number: int


@dataclasses.dataclass(frozen=True)
class ProbeOptions:
    copy_files: bool
    parent_of_root: Pid


@dataclasses.dataclass(frozen=True)
class InodeVersion:
    inode: Inode
    # If you assume no clock adjustemnts, it is monotonic with other mtimes on the same Host;
    # other Hosts will not be synchronized (vector clock).
    # It's better to assume nothing; different mtime still implies different object, but no ordering.
    # mtime nanoseconds precision (whether or not we have nanosecond resolution)
    mtime: numpy.datetime64
    size: int
    other_id: int = 0

    @staticmethod
    def from_local_path(path: pathlib.Path) -> InodeVersion:
        s = path.stat()
        return InodeVersion(
            Inode(
                Host.localhost(),
                Device(
                    os.major(s.st_dev),
                    os.minor(s.st_dev),
                ),
                s.st_ino,
            ),
            numpy.datetime64(s.st_mtime_ns, "ns"),
            s.st_size,
        )

    @staticmethod
    def from_probe_path(path: ops.Path) -> InodeVersion:
        return InodeVersion(
            Inode(
                Host.localhost(),
                Device(path.device_major, path.device_minor),
                path.inode,
            ),
            numpy.datetime64(path.mtime.sec * int(1e9) + path.mtime.nsec, "ns"),
            path.size,
        )

    @staticmethod
    def from_id_string(id_string: str) -> InodeVersion:
        # See `libprobe/src/prov_utils.c:path_to_id_string()`
        array = [
            int(segment, 16)
            for segment in id_string.split("-")
        ]
        assert len(array) == 6
        return InodeVersion(
            Inode(
                Host.localhost(),
                Device(array[0], array[1]),
                array[2],
            ),
            numpy.datetime64(array[3] * int(1e9) + array[4], "ns"),
            array[5],
        )


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
    copied_files: typing.Mapping[InodeVersion, pathlib.Path]
    probe_options: ProbeOptions
    host: Host

    # TODO: refactor
    # I think we should have probe_log.ops[quad] and probe_log.ops -> iterator
    # Maybe drop probe_log.ops -> iterator

    def get_op(self, pid: Pid, exec_no: ExecNo, tid: Tid, op_no: int) -> ops.Op:
        return self.processes[pid].execs[exec_no].threads[tid].ops[op_no]

    def ops(self) -> typing.Iterator[ops.Op]:
        for process in self.processes.values():
            for exec in process.execs.values():
                for thread in exec.threads.values():
                    yield from thread.ops



# TODO: implement this in probe_py.generated.ops
class TaskType(enum.IntEnum):
    TASK_PID = 0
    TASK_TID = 1
    TASK_ISO_C_THREAD = 2
    TASK_PTHREAD = 3


class InvalidProbeLog(Exception):
    pass
