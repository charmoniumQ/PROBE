# This file was @generated by probe_macros
from __future__ import annotations
import typing
from dataclasses import dataclass

# https://github.com/torvalds/linux/blob/73e931504f8e0d42978bfcda37b323dbbd1afc08/include/uapi/linux/fcntl.h#L98
AT_FDCWD: int = -100

@dataclass(init=True, frozen=True)
class Timespec:
    sec: int
    nsec: int


@dataclass(init=True, frozen=True)
class StatxTimestamp:
    sec: int
    nsec: int


@dataclass(init=True, frozen=True)
class Statx:
    mask: int
    blksize: int
    attributes: int
    nlink: int
    uid: int
    gid: int
    mode: int
    ino: int
    size: int
    blocks: int
    attributes_mask: int
    atime: StatxTimestamp
    btime: StatxTimestamp
    ctime: StatxTimestamp
    mtime: StatxTimestamp
    rdev_major: int
    rdev_minor: int
    dev_major: int
    dev_minor: int
    mnt_id: int
    dio_mem_align: int
    dio_offset_align: int


@dataclass(init=True, frozen=True)
class Timeval:
    sec: int
    usec: int


@dataclass(init=True, frozen=True)
class Rusage:
    utime: Timeval
    stime: Timeval
    maxrss: int
    ixrss: int
    idrss: int
    isrss: int
    minflt: int
    majflt: int
    nswap: int
    inblock: int
    oublock: int
    msgsnd: int
    msgrcv: int
    nsignals: int
    nvcsw: int
    nivcsw: int


@dataclass(init=True, frozen=True)
class Path:
    dirfd_minus_at_fdcwd: int
    path: bytes
    device_major: int
    device_minor: int
    inode: int
    mtime: StatxTimestamp
    ctime: StatxTimestamp
    stat_valid: bool
    dirfd_valid: bool

    @property
    def dirfd(self) -> int:
        return self.dirfd_minus_at_fdcwd + AT_FDCWD


@dataclass(init=True, frozen=True)
class InitProcessOp:
    pid: int


@dataclass(init=True, frozen=True)
class InitExecEpochOp:
    epoch: int
    program_name: bytes


@dataclass(init=True, frozen=True)
class InitThreadOp:
    tid: int


@dataclass(init=True, frozen=True)
class OpenOp:
    path: Path
    flags: int
    mode: int
    fd: int
    ferrno: int


@dataclass(init=True, frozen=True)
class CloseOp:
    low_fd: int
    high_fd: int
    ferrno: int


@dataclass(init=True, frozen=True)
class ChdirOp:
    path: Path
    ferrno: int


@dataclass(init=True, frozen=True)
class ExecOp:
    path: Path
    ferrno: int
    argc: int
    argv: list[bytes, ]
    envc: int
    env: list[bytes, ]


@dataclass(init=True, frozen=True)
class CloneOp:
    flags: int
    run_pthread_atfork_handlers: bool
    task_type: int
    task_id: int
    ferrno: int


@dataclass(init=True, frozen=True)
class ExitOp:
    status: int
    run_atexit_handlers: bool


@dataclass(init=True, frozen=True)
class AccessOp:
    path: Path
    mode: int
    flags: int
    ferrno: int


@dataclass(init=True, frozen=True)
class StatOp:
    path: Path
    flags: int
    statx_buf: Statx
    ferrno: int


@dataclass(init=True, frozen=True)
class ReaddirOp:
    dir: Path
    child: bytes
    all_children: bool
    ferrno: int


@dataclass(init=True, frozen=True)
class WaitOp:
    task_type: int
    task_id: int
    options: int
    status: int
    ferrno: int


@dataclass(init=True, frozen=True)
class GetRUsageOp:
    waitpid_arg: int
    getrusage_arg: int
    usage: Rusage
    ferrno: int


@dataclass(init=True, frozen=True)
class ReadLinkOp:
    path: Path
    resolved: bytes
    ferrno: int


@dataclass(init=True, frozen=True)
class UpdateMetadataOp:
    path: Path
    flags: int
    metadata: Metadata
    ferrno: int


@dataclass(init=True, frozen=True)
class Op:
    data: OpInternal
    time: Timespec
    pthread_id: int
    iso_c_thread_id: int


@dataclass(init=True, frozen=True)
class Mode:
    mode: int


@dataclass(init=True, frozen=True)
class Ownership:
    uid: int
    gid: int


@dataclass(init=True, frozen=True)
class Times:
    is_null: bool
    atime: Timeval
    mtime: Timeval


Metadata: typing.TypeAlias = Mode | Ownership | Times
OpInternal: typing.TypeAlias = InitProcessOp | InitExecEpochOp | InitThreadOp | OpenOp | CloseOp | ChdirOp | ExecOp | CloneOp | ExitOp | AccessOp | StatOp | ReaddirOp | WaitOp | GetRUsageOp | UpdateMetadataOp | ReadLinkOp

