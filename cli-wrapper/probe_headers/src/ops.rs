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
pub struct Inode {
    device_major: u32,
    device_minor: u32,
    number: libc::ino_t,
    mode: u16,
    mtime: StatxTimestamp,
    ctime: StatxTimestamp,
    size: u64,
}

// Making this be a struct helps the typing get "stronger"
// Open Numbers can only be used where Open Numbers are expected.
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, PartialEq, Eq, Clone)]
#[repr(C)]
pub struct OpenNumber {
    value: u16,
}

/// cbindgen:prefix-with-name
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, PartialEq, Eq, Clone)]
#[repr(C)]
pub struct PathArg {
    directory: OpenNumber,
    name: Option<ByteString>,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct InitExecEpoch {
    parent_pid: libc::pid_t,
    pid: libc::pid_t,
    epoch: u32,
    exe: PathArg,
    argv: StringArray,
    env: StringArray,
    std_in: Inode,
    std_out: Inode,
    std_err: Inode,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct InitThread {
    tid: libc::pid_t,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Open {
    path: PathArg,
    open_number: OpenNumber,
    inode: Inode,
    flags: libc::c_int,
    mode: libc::mode_t,
    creat: bool,
    dir: bool,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Close {
    open_number: OpenNumber,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Exec {
    path: PathArg,
    inode: Inode,
    argv: StringArray,
    env: StringArray,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Spawn {
    exec: Exec,
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
pub struct Clone {
    flags: libc::c_int,
    run_pthread_atfork_handlers: bool,
    task_type: TaskType,
    task_id: i64,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct ExitProcess {
    status: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct ExitThread {
    status: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Access {
    path: PathArg,
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
pub struct Stat {
    path: PathArg,
    flags: libc::c_int,
    stat_result: StatResult,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Readdir {
    dir: PathArg,
    child: Option<ByteString>,
    all_children: bool,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Wait {
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

// Note that all types participating in an enum should be structs.
// So that we can put the "type" tag in there.
#[derive(MemoryParsable, JsonSchema, Serialize, Debug)]
#[repr(C)]
#[derive(Clone)]
pub struct Mode {
    value: libc::mode_t,
}

/// cbindgen:prefix-with-name
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(u8)]
#[serde(tag = "type")]
pub enum MetadataValue {
    Mode(Mode),
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
pub struct UpdateMetadata {
    path: PathArg,
    flags: libc::c_int,
    value: MetadataValue,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct ReadLink {
    linkpath: PathArg,
    referent: ByteString,
    truncation: bool,
    recursive_dereference: bool,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Dup {
    old: OpenNumber,
    flags: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct HardLink {
    old: PathArg,
    new: PathArg,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct SymbolicLink {
    old: ByteString,
    new: PathArg,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Unlink {
    path: PathArg,
    unlink_type: libc::c_int,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct Rename {
    src: PathArg,
    dst: PathArg,
}

#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(C)]
pub struct MkFile {
    path: PathArg,
    file_type: FileType,
}

/// cbindgen:prefix-with-name
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(u8)]
pub enum FileType {
    Dir,
    Fifo,
    Pipe,
}

/// cbindgen:add-sentinel
/// cbindgen:prefix-with-name
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
#[repr(u8)]
#[serde(tag = "type")]
pub enum OpData {
    Access(Access),
    Clone(Clone),
    Close(Close),
    Dup(Dup),
    Exec(Exec),
    ExitProcess(ExitProcess),
    ExitThread(ExitThread),
    HardLink(HardLink),
    InitExecEpoch(InitExecEpoch),
    InitThread(InitThread),
    Open(Open),
    ReadLink(ReadLink),
    Readdir(Readdir),
    Rename(Rename),
    Spawn(Spawn),
    Stat(Stat),
    SymbolicLink(SymbolicLink),
    Unlink(Unlink),
    UpdateMetadata(UpdateMetadata),
    Wait(Wait),
    MkFile(MkFile),
}

// echo -e '#include <stdio.h>\\n#include <threads.h>\\nint main() { printf("%ld %ld\\\\n", sizeof(thrd_t), sizeof(thrd_start_t)); return 0; }' | gcc -Og -g -x c - && ./a.out && rm a.out
// prints 8 8

#[repr(C)]
#[derive(MemoryParsable, JsonSchema, Serialize, Debug, Clone)]
pub struct Op {
    data: OpData,
    pthread_id: u16,
    iso_c_thread_id: u64,
    ferrno: libc::c_int,
}
