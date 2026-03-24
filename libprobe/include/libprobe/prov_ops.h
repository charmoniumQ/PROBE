#pragma once

#define _GNU_SOURCE

#include <features.h>  // for __GLIBC_MINOR__, __GLIBC__
#include <stdbool.h>   // for bool, false
#include <stddef.h>    // for size_t
#include <stdint.h>    // for uint32_t, int32_t, uint64_t, int64_t
#include <sys/types.h> // for pid_t, mode_t, gid_t, ino_t, uid_t
// IWYU pragma: no_include "bits/pthreadtypes.h" for pthread_t
// IWYU pragma: no_include "linux/stat.h" for statx_timestamp

typedef char const* _Nonnull ByteString;
typedef char const* _Nullable Option_ByteString;
typedef char const* _Nullable const* _Nonnull StringArray;

typedef int64_t TimeT;

typedef int64_t SusecondsT;

struct TimeVal {
    TimeT tv_sec;
    SusecondsT tv_usec;
};

struct StatxTimestamp {
    long long tv_sec;
    unsigned int tv_nsec;
    unsigned int __padding;
};

struct Rusage {
    struct TimeVal ru_utime;
    struct TimeVal ru_stime;
    long ru_maxrss;
    long ru_ixrss;
    long ru_idrss;
    long ru_isrss;
    long ru_minflt;
    long ru_majflt;
    long ru_nswap;
    long ru_inblock;
    long ru_oublock;
    long ru_msgsnd;
    long ru_msgrcv;
    long ru_nsignals;
    long ru_nvcsw;
    long ru_nivcsw;
};

struct Path {
    int32_t dirfd;
    const char* _Nullable path; /* valid if non-null */
    /* rest are valid if stat_valid */
    unsigned int device_major;
    unsigned int device_minor;
    ino_t inode;
    uint16_t mode;
    struct StatxTimestamp mtime;
    struct StatxTimestamp ctime;
    size_t size;
    bool stat_valid;
};

struct InitExecEpochOp {
    pid_t parent_pid;
    pid_t pid;
    unsigned int epoch;
    struct Path cwd;
    struct Path exe;
    StringArray argv;
    StringArray env;
    struct Path std_in;
    struct Path std_out;
    struct Path std_err;
};

struct InitThreadOp {
    pid_t tid;
};

struct OpenOp {
    struct Path path;
    int flags;
    mode_t mode;
    int32_t fd;
    int ferrno;
    /* Note, we use ferrno in these structs because errno is something magical (maybe a macro?) */
};

struct CloseOp {
    int32_t fd;
    int ferrno;
    struct Path path;
};

struct ChdirOp {
    struct Path path;
    int ferrno;
};

struct ExecOp {
    struct Path path;
    int ferrno;
    StringArray argv;
    StringArray env;
};

struct SpawnOp {
    struct ExecOp exec;
    pid_t child_pid;
    int ferrno;
};

enum TaskType {
    TaskType_Pid,
    TaskType_Tid,
    TaskType_IsoCThread,
    TaskType_Pthread,
};

struct CloneOp {
    int flags;
    bool run_pthread_atfork_handlers;
    enum TaskType task_type;
    int64_t task_id;
    int ferrno;
};

struct ExitProcessOp {
    int status;
};

struct ExitThreadOp {
    int status;
};

struct AccessOp {
    struct Path path;
    int mode;
    int flags;
    int ferrno;
};

struct StatResult {
    uint32_t mask;
    uint32_t nlink;
    uint32_t uid;
    uint32_t gid;
    uint16_t mode;
    uint64_t ino;
    uint64_t size;
    uint64_t blocks;
    uint32_t blksize;
    struct StatxTimestamp atime;
    struct StatxTimestamp btime;
    struct StatxTimestamp ctime;
    struct StatxTimestamp mtime;
    uint32_t dev_major;
    uint32_t dev_minor;
};

struct StatOp {
    struct Path path;
    int flags;
    int ferrno;
    struct StatResult stat_result;
};

struct ReaddirOp {
    struct Path dir;
    char* _Nullable child;
    bool all_children;
    int ferrno;
};

/*
 * There are user threads (ISO C threads and POSIX threads) and hardware threads (clone/wait4).
 *
 * Hardware thread ID is most relevant for ordering synchronization ops. E.g.,
 * when we hit a mutex, we should record which thread/op we are.
 *
 * However, we need the ISO C thread ID and POSIX thread ID to identify thread
 * the target of creation and joining.
 *
 * thrd_t is "A unique object that identifies a thread." [glibc doc](https://www.gnu.org/software/libc/manual/html_node/ISO-C-Thread-Management.html).
 *
 * How big is it?
 *
 *     echo -e '#include <stdio.h>\n#include <threads.h>\nint main() { printf("%ld\\n", sizeof(thrd_t)); return 0; }' \
 *     | gcc -Og -g -x c - && ./a.out && rm a.out
 *     8
 *
 * Therefore, we will use int64_t for task_id.
 *
 * On the other hand, pthread is not that.
 *
 *        POSIX.1 allows an implementation wide freedom in choosing the type
 *        used to represent a thread ID; for example, representation using
 *        either an arithmetic type or a structure is permitted.  Therefore,
 *        variables of type pthread_t can't portably be compared using the C
 *        equality operator (==); use pthread_equal(3) instead.
 *        --- [man pthread_self](https://www.man7.org/linux/man-pages/man3/pthread_self.3.html)
 *
 * We will track those by creating our own pthread identifier using an atomic
 * counter and pthread_set/getspecific.
 */

struct WaitOp {
    enum TaskType task_type;
    int64_t task_id;
    int options;
    int status;
    bool cancelled;
    struct Rusage usage;
    int ferrno;
};

struct Ownership {
    uid_t uid;
    gid_t gid;
};

struct Times {
    bool is_null;
    struct TimeVal atime;
    struct TimeVal mtime;
};

enum MetadataValue_Tag {
    MetadataValue_Mode,
    MetadataValue_Ownership,
    MetadataValue_Times,
};

union MetadataValue {
    enum MetadataValue_Tag tag;
    struct {
        enum MetadataValue_Tag mode_tag;
        mode_t mode;
    };
    struct {
        enum MetadataValue_Tag ownership_tag;
        struct Ownership ownership;
    };
    struct {
        enum MetadataValue_Tag times_tag;
        struct Times times;
    };
};

struct UpdateMetadataOp {
    struct Path path;
    int flags;
    union MetadataValue value;
    int ferrno;
};

struct ReadLinkOp {
    struct Path linkpath;
    const char* _Nullable referent;
    bool truncation;
    bool recursive_dereference;
    int ferrno;
};

struct DupOp {
    struct Path path;
    int old;
    int new_;
    int flags;
    int ferrno;
};

struct HardLinkOp {
    struct Path old;
    struct Path new_;
    int ferrno;
};

struct SymbolicLinkOp {
    const char* _Nullable old;
    struct Path new_;
    int ferrno;
};

struct UnlinkOp {
    struct Path path;
    int unlink_type;
    int ferrno;
};

struct RenameOp {
    struct Path src;
    struct Path dst;
    int ferrno;
};

enum FileType {
    FileType_Dir,
    FileType_Fifo,
    FileType_Pipe,
};

struct MkFileOp {
    struct Path path;
    enum FileType file_type;
    int flags;
    mode_t mode;
    int ferrno;
};

enum OpData_Tag {
    OpData_Access,
    OpData_Chdir,
    OpData_Clone,
    OpData_Close,
    OpData_Dup,
    OpData_Exec,
    OpData_ExitProcess,
    OpData_ExitThread,
    OpData_HardLink,
    OpData_InitExecEpoch,
    OpData_InitThread,
    OpData_MkFile,
    OpData_Open,
    OpData_ReadLink,
    OpData_Readdir,
    OpData_Rename,
    OpData_Spawn,
    OpData_Stat,
    OpData_SymbolicLink,
    OpData_Unlink,
    OpData_UpdateMetadata,
    OpData_Wait,
    /**
     * Must be last for serialization purposes
     */
    OpData_Sentinel,
};

union OpData {
    enum OpData_Tag tag;
    struct {
        enum OpData_Tag access_tag;
        struct AccessOp access;
    };
    struct {
        enum OpData_Tag chdir_tag;
        struct ChdirOp chdir;
    };
    struct {
        enum OpData_Tag clone_tag;
        struct CloneOp clone;
    };
    struct {
        enum OpData_Tag close_tag;
        struct CloseOp close;
    };
    struct {
        enum OpData_Tag dup_tag;
        struct DupOp dup;
    };
    struct {
        enum OpData_Tag exec_tag;
        struct ExecOp exec;
    };
    struct {
        enum OpData_Tag exit_process_tag;
        struct ExitProcessOp exit_process;
    };
    struct {
        enum OpData_Tag exit_thread_tag;
        struct ExitThreadOp exit_thread;
    };
    struct {
        enum OpData_Tag hard_link_tag;
        struct HardLinkOp hard_link;
    };
    struct {
        enum OpData_Tag init_exec_epoch_tag;
        struct InitExecEpochOp init_exec_epoch;
    };
    struct {
        enum OpData_Tag init_thread_tag;
        struct InitThreadOp init_thread;
    };
    struct {
        enum OpData_Tag mk_file_tag;
        struct MkFileOp mk_file;
    };
    struct {
        enum OpData_Tag open_tag;
        struct OpenOp open;
    };
    struct {
        enum OpData_Tag read_link_tag;
        struct ReadLinkOp read_link;
    };
    struct {
        enum OpData_Tag readdir_tag;
        struct ReaddirOp readdir;
    };
    struct {
        enum OpData_Tag rename_tag;
        struct RenameOp rename;
    };
    struct {
        enum OpData_Tag spawn_tag;
        struct SpawnOp spawn;
    };
    struct {
        enum OpData_Tag stat_tag;
        struct StatOp stat;
    };
    struct {
        enum OpData_Tag symbolic_link_tag;
        struct SymbolicLinkOp symbolic_link;
    };
    struct {
        enum OpData_Tag unlink_tag;
        struct UnlinkOp unlink;
    };
    struct {
        enum OpData_Tag update_metadata_tag;
        struct UpdateMetadataOp update_metadata;
    };
    struct {
        enum OpData_Tag wait_tag;
        struct WaitOp wait;
    };
};

struct Op {
    union OpData data;
    uint16_t pthread_id;
    uint64_t iso_c_thread_id;
};

/* We don't need this since we switched to an Arena allocator */
/* static void free_op(struct Op op); */
