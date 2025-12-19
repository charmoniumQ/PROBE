#pragma once

#define _GNU_SOURCE

#include <features.h>  // for __GLIBC_MINOR__, __GLIBC__
#include <stdbool.h>   // for bool, false
#include <stdint.h>    // for uint32_t, int32_t, uint64_t, int64_t
#include <sys/time.h>  // for timeval
#include <sys/types.h> // for pid_t, mode_t, gid_t, ino_t, uid_t
#include <time.h>      // for timespec
// IWYU pragma: no_include "bits/pthreadtypes.h" for pthread_t
// IWYU pragma: no_include "linux/stat.h" for statx_timestamp

#if defined(__GLIBC__) && __GLIBC_MINOR__ >= 28
#include <threads.h> // for thrd_t, thrd_start_t
#else
// echo -e '#include <stdio.h>\\n#include <threads.h>\\nint main() { printf("%ld %ld\\\\n", sizeof(thrd_t), sizeof(thrd_start_t)); return 0; }' | gcc -Og -g -x c - && ./a.out && rm a.out
// prints 8 8
typedef uint64_t thrd_t;
typedef uint64_t thrd_start_t;
#error "I don't expect this branch to be used, but it should still work"
// See ./PROBE/docs/old-glibc.md
#endif

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

typedef uint16_t OpenNumber;

struct Timestamp {
    int64_t tv_sec;
    uint32_t tv_nsec;
};

struct StatxTruncated {
    /* This struct is a truncation of the statx struct.
     * https://www.man7.org/linux/man-pages/man2/statx.2.html
     * */
    uint32_t stx_mask;
    uint32_t stx_blksize;
    uint64_t stx_attributes;
    uint32_t stx_nlink;
    uint32_t stx_uid;
    uint32_t stx_gid;
    uint16_t stx_mode;
    uint64_t stx_ino;
    uint64_t stx_size;
    uint64_t stx_blocks;
    uint64_t stx_attributes_mask;
    struct Timestamp stx_atime;
    struct Timestamp stx_btime;
    struct Timestamp stx_ctime;
    struct Timestamp stx_mtime;
    uint32_t stx_rdev_major;
    uint32_t stx_rdev_minor;
    uint32_t stx_dev_major;
    uint32_t stx_dev_minor;
};

struct Path2 {
    int32_t dirfd_minus_at_fdcwd;
    OpenNumber dirfd_open_number;
    const char* path;
};

struct InitExecEpochOp {
    pid_t parent_pid;
    pid_t pid;
    unsigned int epoch;
    char* const* argv;
    char* const* env;
};

struct InitThreadOp {
    pid_t tid;
};

struct OpenOp {
    struct Path2 path;
    int fd;
    OpenNumber open_number;
    struct StatxTruncated stat;
    int flags;
    mode_t mode;
};

struct CloseOp {
    OpenNumber open_number;
    int fd;
};

struct ExecOp {
    struct Path2 path;
    // FIXME: exec should get marked as a read
    char* const* argv;
    char* const* env;
};

struct SpawnOp {
    struct ExecOp exec;
    pid_t child_pid;
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
};

struct ExitProcessOp {
    int status;
};

struct ExitThreadOp {
    int status;
};

struct AccessOp {
    struct Path2 path;
    int mode;
    int flags;
};

struct StatOp {
    struct Path2 path;
    int flags;
    struct StatxTruncated statx_buf;
};

struct ReaddirOp {
    struct Path2 dir;
    const char* child;
    bool all_children;
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
    struct Path2 path;
    int flags;
    enum MetadataKind kind;
    union MetadataValue value;
};

struct ReadLinkOp {
    struct Path2 linkpath;
    const char* referent;
    bool truncation;
    bool recursive_dereference;
};

struct DupOp {
    int old;
    int new;
    OpenNumber dupped;
    OpenNumber closed;
    int flags;
};

struct HardLinkOp {
    struct Path2 old;
    struct Path2 new;
};

struct SymbolicLinkOp {
    const char* old;
    struct Path2 new;
};

struct UnlinkOp {
    struct Path2 path;
    int unlink_type;
};

struct RenameOp {
    struct Path2 src;
    struct Path2 dst;
};

enum FileType {
    DirFileType,
    FifoFileType,
    PipeFileType,
};

struct MkFileOp {
    struct Path2 path;
    enum FileType file_type;
    int flags;
    mode_t mode;
};

enum OpCode {
    FIRST_OP_CODE,
    init_process_op_code,
    init_exec_epoch_op_code,
    init_thread_op_code,
    open_op_code,
    close_op_code,
    exec_op_code,
    spawn_op_code,
    clone_op_code,
    exit_thread_op_code,
    exit_process_op_code,
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
        struct ExecOp exec;
        struct SpawnOp spawn;
        struct CloneOp clone;
        struct ExitThreadOp exit_thread;
        struct ExitProcessOp exit_process;
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

    /* Note, we use ferrno in these structs because errno is something magical (maybe a macro?) */
    uint16_t ferrno;

    // TODO: eliminate this
    uint16_t pthread_id;
    thrd_t iso_c_thread_id;    
};

/* We don't need this since we switched to an Arena allocator */
/* static void free_op(struct Op op); */
