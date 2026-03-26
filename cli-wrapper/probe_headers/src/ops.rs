use derive_memory_parsing::MemoryParsable;
use memory_parsing::{ByteString, StringArray};
use schemars::JsonSchema;
use serde::Serialize;
use std::fmt::Debug;

// echo -e '#include <time.h>\n#include <sys/types.h>\n#include <stdio.h>\n#include <threads.h>\nint main() { printf("%ld %ld\\\\n", sizeof(time_t), sizeof(suseconds_t)); return 0; }' | gcc -Og -g -x c - && ./a.out && rm a.out
type TimeT = i64;
type SusecondsT = i64;

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct TimeVal {
    tv_sec: TimeT,
    tv_usec: SusecondsT,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Rusage {
    ru_utime: TimeVal,
    ru_stime: TimeVal,
    ru_maxrss: libc::c_long,
    ru_ixrss: libc::c_long,
    ru_idrss: libc::c_long,
    ru_isrss: libc::c_long,
    ru_minflt: libc::c_long,
    ru_majflt: libc::c_long,
    ru_nswap: libc::c_long,
    ru_inblock: libc::c_long,
    ru_oublock: libc::c_long,
    ru_msgsnd: libc::c_long,
    ru_msgrcv: libc::c_long,
    ru_nsignals: libc::c_long,
    ru_nvcsw: libc::c_long,
    ru_nivcsw: libc::c_long,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, PartialEq, Eq, Clone)]
#[repr(C)]
pub struct StatxTimestamp {
    tv_sec: libc::c_longlong,
    tv_nsec: libc::c_uint,

    #[serde(skip)]
    __padding: libc::c_uint,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, PartialEq, Eq, Clone)]
#[repr(C)]
pub struct Path {
    dirfd: i32,
    path: Option<ByteString>,
    device_major: u32,
    device_minor: u32,
    inode: libc::ino_t,
    mode: u16,
    mtime: StatxTimestamp,
    ctime: StatxTimestamp,
    size: u64,
    stat_valid: bool,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct InitExecEpochOp {
    parent_pid: libc::pid_t,
    pid: libc::pid_t,
    epoch: u32,
    cwd: Path,
    exe: Path,
    argv: StringArray,
    env: StringArray,
    std_in: Path,
    std_out: Path,
    std_err: Path,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct InitThreadOp {
    tid: libc::pid_t,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct OpenOp {
    path: Path,
    flags: libc::c_int,
    mode: libc::mode_t,
    fd: i32,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct CloseOp {
    fd: i32,
    path: Path,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct ExecOp {
    path: Path,
    argv: StringArray,
    env: StringArray,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct SpawnOp {
    exec: ExecOp,
    child_pid: libc::pid_t,
}

/// cbindgen:prefix-with-name
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(u8)]
pub enum TaskType {
    Pid,
    Tid,
    IsoCThread,
    Pthread,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct CloneOp {
    flags: libc::c_int,
    run_pthread_atfork_handlers: bool,
    task_type: TaskType,
    task_id: i64,
    }

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct ExitProcessOp {
    status: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct ExitThreadOp {
    status: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct AccessOp {
    path: Path,
    mode: libc::c_int,
    flags: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct StatResult {
    mask: u32,
    nlink: u32,
    uid: u32,
    gid: u32,
    mode: u16,
    #[serde(skip)]
    __padding0: u16,
    ino: u64,
    size: u64,
    blocks: u64,
    blksize: u32,
    atime: StatxTimestamp,
    btime: StatxTimestamp,
    ctime: StatxTimestamp,
    mtime: StatxTimestamp,
    dev_major: u32,
    dev_minor: u32,
    #[serde(skip)]
    __padding1: [u64; 12],
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct StatOp {
    path: Path,
    flags: libc::c_int,
    stat_result: StatResult,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct ReaddirOp {
    dir: Path,
    child: Option<ByteString>,
    all_children: bool,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct WaitOp {
    task_type: TaskType,
    task_id: i64,
    options: libc::c_int,
    status: libc::c_int,
    cancelled: bool,
    usage: Rusage,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug)]
#[repr(C)]
#[derive(Clone)]
pub struct Ownership {
    uid: libc::uid_t,
    gid: libc::gid_t,
}

/// cbindgen:prefix-with-name
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(u8)]
#[serde(tag = "type", content = "content")]
pub enum MetadataValue {
    Mode(libc::mode_t),
    Ownership(Ownership),
    Times(Times),
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Times {
    is_null: bool,
    atime: TimeVal,
    mtime: TimeVal,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct UpdateMetadataOp {
    path: Path,
    flags: libc::c_int,
    value: MetadataValue,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct ReadLinkOp {
    linkpath: Path,
    referent: ByteString,
    truncation: bool,
    recursive_dereference: bool,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct DupOp {
    path: Path,
    old: libc::c_int,
    new: libc::c_int,
    flags: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct HardLinkOp {
    old: Path,
    new: Path,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct SymbolicLinkOp {
    old: ByteString,
    new: Path,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct UnlinkOp {
    path: Path,
    unlink_type: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct RenameOp {
    src: Path,
    dst: Path,
}

/// cbindgen:prefix-with-name
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(u8)]
pub enum FileType {
    Dir,
    Fifo,
    Pipe,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct MkFileOp {
    path: Path,
    file_type: FileType,
    flags: libc::c_int,
    mode: libc::mode_t,
}

/// cbindgen:add-sentinel
/// cbindgen:prefix-with-name
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(u8)]
#[allow(clippy::large_enum_variant)] /* TODO: reduce op size */
#[serde(tag = "type", content = "content")]
pub enum OpData {
    Access(AccessOp),
    Clone(CloneOp),
    Close(CloseOp),
    Dup(DupOp),
    Exec(ExecOp),
    ExitProcess(ExitProcessOp),
    ExitThread(ExitThreadOp),
    HardLink(HardLinkOp),
    InitExecEpoch(InitExecEpochOp),
    InitThread(InitThreadOp),
    MkFile(MkFileOp),
    Open(OpenOp),
    ReadLink(ReadLinkOp),
    Readdir(ReaddirOp),
    Rename(RenameOp),
    Spawn(SpawnOp),
    Stat(StatOp),
    SymbolicLink(SymbolicLinkOp),
    Unlink(UnlinkOp),
    UpdateMetadata(UpdateMetadataOp),
    Wait(WaitOp),
}

// echo -e '#include <stdio.h>\\n#include <threads.h>\\nint main() { printf("%ld %ld\\\\n", sizeof(thrd_t), sizeof(thrd_start_t)); return 0; }' | gcc -Og -g -x c - && ./a.out && rm a.out
// prints 8 8

#[repr(C)]
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
pub struct Op {
    #[serde(rename = "data_tagged")]
    data: OpData,
    pthread_id: u16,
    iso_c_thread_id: u64,
    ferrno: libc::c_int,
}
