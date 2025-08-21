#pragma once

#define _GNU_SOURCE

#include <stdbool.h>   // for bool, false
#include <stddef.h>    // for size_t, NULL
#include <stdint.h>    // for uint32_t, int32_t, uint64_t, int64_t
#include <sys/stat.h>  // IWYU pragma: keep for statx_timestamp
#include <sys/time.h>  // for timeval
#include <sys/types.h> // for pid_t, mode_t, gid_t, ino_t, uid_t
#include <threads.h>   // for thrd_t
#include <time.h>      // for timespec
// IWYU pragma: no_include "bits/pthreadtypes.h" for pthread_t
// IWYU pragma: no_include "linux/stat.h" for statx_timestamp

// HACK: defining this manually instead of using <sys/resource.h> is
// a huge hack, but it greatly reduces the generated code complexity
// since in glibc all the long ints are unions over two types that
// both alias to long int, this is done for kernel-userland
// compatibility reasons that don't matter here.
struct my_rusage {
    struct timeval ru_utime;
    struct timeval ru_stime;
    long int ru_maxrss;
    long int ru_ixrss;
    long int ru_idrss;
    long int ru_isrss;
    long int ru_minflt;
    long int ru_majflt;
    long int ru_nswap;
    long int ru_inblock;
    long int ru_oublock;
    long int ru_msgsnd;
    long int ru_msgrcv;
    long int ru_nsignals;
    long int ru_nvcsw;
    long int ru_nivcsw;
};

struct Path {
    int32_t dirfd_minus_at_fdcwd;
    const char* path; /* path valid if non-null */
    unsigned int device_major;
    unsigned int device_minor;
    ino_t inode;
    uint16_t mode;
    struct statx_timestamp mtime;
    struct statx_timestamp ctime;
    size_t size;
    bool stat_valid;
    bool dirfd_valid;
};

static const struct Path null_path = {-1, NULL, -1, -1, -1, 0, {0}, {0}, 0, false, false};
/* We don't need to free paths since I switched to the Arena allocator */
/* static void free_path(struct Path path); */

struct InitExecEpochOp {
    pid_t parent_pid;
    pid_t pid;
    unsigned int epoch;
    struct Path cwd;
    struct Path exe;
    char* const* argv;
    char* const* env;
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
    char* const* argv;
    char* const* env;
};

struct SpawnOp {
    struct ExecOp exec;
    pid_t child_pid;
    int ferrno;
};

enum TaskType {
    TASK_PID,
    TASK_TID,
    TASK_ISO_C_THREAD,
    TASK_PTHREAD,
};

struct CloneOp {
    int flags;
    bool run_pthread_atfork_handlers;
    enum TaskType task_type;
    int64_t task_id;
    int ferrno;
};

struct ExitOp {
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
    struct statx_timestamp atime;
    struct statx_timestamp btime;
    struct statx_timestamp ctime;
    struct statx_timestamp mtime;
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
    char* child;
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
    struct my_rusage usage;
    int ferrno;
};

enum MetadataKind {
    MetadataMode,
    MetadataOwnership,
    MetadataTimes,
};

union MetadataValue {
    mode_t mode;
    struct {
        uid_t uid;
        gid_t gid;
    } ownership;
    struct {
        bool is_null;
        struct timeval atime;
        struct timeval mtime;
    } times;
};

struct UpdateMetadataOp {
    struct Path path;
    int flags;
    enum MetadataKind kind;
    union MetadataValue value;
    int ferrno;
};

struct ReadLinkOp {
    struct Path linkpath;
    const char* referent;
    bool truncation;
    bool recursive_dereference;
    int ferrno;
};

struct DupOp {
    int old;
    int new;
    int flags;
    int ferrno;
};

struct HardLinkOp {
    struct Path old;
    struct Path new;
    int ferrno;
};

struct SymbolicLinkOp {
    const char* old;
    struct Path new;
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
    DirFileType,
    FifoFileType,
};

struct MkFileOp {
    struct Path path;
    enum FileType file_type;
    int flags;
    mode_t mode;
    int ferrno;
};

enum OpCode {
    FIRST_OP_CODE,
    init_process_op_code,
    init_exec_epoch_op_code,
    init_thread_op_code,
    open_op_code,
    close_op_code,
    chdir_op_code,
    exec_op_code,
    spawn_op_code,
    clone_op_code,
    exit_op_code,
    access_op_code,
    stat_op_code,
    readdir_op_code,
    wait_op_code,
    update_metadata_op_code,
    read_link_op_code,
    dup_op_code,
    hard_link_op_code,
    symbolic_link_op_code,
    unlink_op_code,
    rename_op_code,
    mkfile_op_code,
    LAST_OP_CODE,
};

struct Op {
    enum OpCode op_code;
    union {
        struct InitExecEpochOp init_exec_epoch;
        struct InitThreadOp init_thread;
        struct OpenOp open;
        struct CloseOp close;
        struct ChdirOp chdir;
        struct ExecOp exec;
        struct SpawnOp spawn;
        struct CloneOp clone;
        struct ExitOp exit;
        struct AccessOp access;
        struct StatOp stat;
        struct ReaddirOp readdir;
        struct WaitOp wait;
        struct UpdateMetadataOp update_metadata;
        struct ReadLinkOp read_link;
        struct DupOp dup;
        struct HardLinkOp hard_link;
        struct SymbolicLinkOp symbolic_link;
        struct UnlinkOp unlink;
        struct RenameOp rename;
        struct MkFileOp mkfile;
    } data;
    struct timespec time;
    uint16_t pthread_id;
    thrd_t iso_c_thread_id;
};

/* We don't need this since we switched to an Arena allocator */
/* static void free_op(struct Op op); */
