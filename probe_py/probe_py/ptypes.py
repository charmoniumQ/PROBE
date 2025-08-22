from __future__ import annotations
import dataclasses
import enum
import hmac
import functools
import os
import pathlib
import random
import socket
import stat
import typing
import networkx
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
    name: str
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
    def __str__(self) -> str:
        return f"device {self.major_id}_{self.minor_id}"


@dataclasses.dataclass(frozen=True)
class Inode:
    host: Host
    device: Device
    number: int
    mode: int

    @property
    def type(self) -> str:
        return stat.filemode(self.mode)[0]

    @property
    def is_fifo(self) -> bool:
        return stat.S_ISFIFO(self.mode)

    def __str__(self) -> str:
        return f"inode {self.type.upper()} {self.number} on {self.device} @{self.host.name}"


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
                s.st_mode,
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
                path.mode,
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
                0,
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
class OpQuad:
    pid: Pid
    exec_no: ExecNo
    tid: Tid
    op_no: int

    def thread_triple(self) -> tuple[Pid, ExecNo, Tid]:
        return (self.pid, self.exec_no, self.tid)

    def __str__(self) -> str:
        return f"PID {self.pid} Exec {self.exec_no} TID {self.tid} op {self.op_no}"


@dataclasses.dataclass(frozen=True)
class OpQuint(OpQuad):
    deduplicator: int

    def deduplicate(self, other: OpQuad) -> OpQuint:
        if self.quad() != other:
            return OpQuint.from_quad(other, 0)
        else:
            return OpQuint.from_quad(other, self.deduplicator + 1)

    @staticmethod
    def from_quad(quad: OpQuad, deduplicator: int = 0) -> OpQuint:
        return OpQuint(quad.pid, quad.exec_no, quad.tid, quad.op_no, deduplicator)

    def quad(self) -> OpQuad:
        return OpQuad(self.pid, self.exec_no, self.tid, self.op_no)


@dataclasses.dataclass(frozen=True)
class ProbeLog:
    processes: typing.Mapping[Pid, Process]
    copied_files: typing.Mapping[InodeVersion, pathlib.Path]
    probe_options: ProbeOptions
    host: Host

    # TODO: refactor
    # I think we should have probe_log.ops[quad] and probe_log.ops -> iterator
    # Maybe drop probe_log.ops -> iterator

    def get_op(self, op: OpQuad) -> ops.Op:
        return self.processes[op.pid].execs[op.exec_no].threads[op.tid].ops[op.op_no]

    def ops(self) -> typing.Iterator[tuple[OpQuad, ops.Op]]:
        for pid, process in sorted(self.processes.items()):
            for epoch, exec in sorted(process.execs.items()):
                for tid, thread in sorted(exec.threads.items()):
                    for op_no, op in enumerate(thread.ops):
                        yield OpQuad(pid, epoch, tid, op_no), op

    def get_root_pid(self) -> Pid:
        for quad, op in self.ops():
            match op.data:
                case ops.InitExecEpochOp():
                    if op.data.parent_pid == self.probe_options.parent_of_root:
                        return Pid(quad.pid)
        raise RuntimeError("No root process found")

    def get_parent_pid_map(self) -> typing.Mapping[Pid, Pid]:
        parent_pid_map = dict[Pid, Pid]()
        for quad, op in self.ops():
            match op.data:
                case ops.CloneOp():
                    if op.data.ferrno == 0 and op.data.task_type == TaskType.TASK_PID:
                        parent_pid_map[Pid(op.data.task_id)] = quad.pid
                case ops.SpawnOp():
                    if op.data.ferrno == 0:
                        parent_pid_map[Pid(op.data.child_pid)] = quad.pid
        return parent_pid_map

    def n_ops(self) -> int:
        total = 0
        for pid, process in sorted(self.processes.items()):
            for epoch, exec in sorted(process.execs.items()):
                for tid, thread in sorted(exec.threads.items()):
                    total += len(thread.ops)
        return total


# TODO: implement this in probe_py.generated.ops
class TaskType(enum.IntEnum):
    TASK_PID = 0
    TASK_TID = 1
    TASK_ISO_C_THREAD = 2
    TASK_PTHREAD = 3


class InvalidProbeLog(Exception):
    pass


class UnusualProbeLog(Warning):
    pass


class AccessMode(enum.IntEnum):
    """In what way are we accessing the inode version?"""
    EXEC = enum.auto()
    DLOPEN = enum.auto()
    READ = enum.auto()
    WRITE = enum.auto()
    READ_WRITE = enum.auto()
    TRUNCATE_WRITE = enum.auto()

    @property
    def has_input(self) -> bool:
        return self in {AccessMode.EXEC, AccessMode.DLOPEN, AccessMode.READ, AccessMode.READ_WRITE}

    @property
    def is_mutation(self) -> bool:
        return self in {AccessMode.WRITE, AccessMode.READ_WRITE}

    @property
    def has_output(self) -> bool:
        return self in {AccessMode.WRITE, AccessMode.READ_WRITE, AccessMode.TRUNCATE_WRITE}

    @staticmethod
    def from_open_flags(flags: int) -> "AccessMode":
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
            raise InvalidProbeLog(f"Invalid open flags: 0x{flags:x}")


class Phase(enum.StrEnum):
    BEGIN = enum.auto()
    END = enum.auto()


@dataclasses.dataclass
class Access:
    phase: Phase
    mode: AccessMode
    inode: Inode
    path: pathlib.Path
    op_node: OpQuad
    fd: int | None

if typing.TYPE_CHECKING:
    HbGraph: typing.TypeAlias = networkx.DiGraph[OpQuad]
else:
    HbGraph = networkx.DiGraph
