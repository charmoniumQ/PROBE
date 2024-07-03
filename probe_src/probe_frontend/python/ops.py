# This file was @generated by probe_macros
from __future__ import annotations
import typing
from dataclasses import dataclass

@dataclass(init=True, frozen=True)
class Timespec:
    tv_sec: int
    tv_nsec: int

@dataclass(init=True, frozen=True)
class StatxTimestamp:
    tv_sec: int
    tv_nsec: int

@dataclass(init=True, frozen=True)
class Statx:
    stx_mask: int
    stx_blksize: int
    stx_attributes: int
    stx_nlink: int
    stx_uid: int
    stx_gid: int
    stx_mode: int
    stx_ino: int
    stx_size: int
    stx_blocks: int
    stx_attributes_mask: int
    stx_atime: StatxTimestamp
    stx_btime: StatxTimestamp
    stx_ctime: StatxTimestamp
    stx_mtime: StatxTimestamp
    stx_rdev_major: int
    stx_rdev_minor: int
    stx_dev_major: int
    stx_dev_minor: int
    stx_mnt_id: int
    stx_dio_mem_align: int
    stx_dio_offset_align: int

@dataclass(init=True, frozen=True)
class Timeval:
    tv_sec: int
    tv_usec: int

@dataclass(init=True, frozen=True)
class Rusage:
    ru_utime: Timeval
    ru_stime: Timeval
    ru_maxrss: int
    ru_ixrss: int
    ru_idrss: int
    ru_isrss: int
    ru_minflt: int
    ru_majflt: int
    ru_nswap: int
    ru_inblock: int
    ru_oublock: int
    ru_msgsnd: int
    ru_msgrcv: int
    ru_nsignals: int
    ru_nvcsw: int
    ru_nivcsw: int

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

@dataclass(init=True, frozen=True)
class CloneOp:
    flags: int
    run_pthread_atfork_handlers: bool
    child_process_id: int
    child_thread_id: int
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
    pid: int
    options: int
    status: int
    ret: int
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

