#ifdef PYCPARSER
#define _BITS_BYTESWAP_H
#define __attribute__(x)
#define __bswap_64(x)
#define __restrict
#define __inline
#define __extension__
#define BORROWED
#define OWNED
#define _GNU_SOURCE
#define __signed__ signed
#include <stdint.h>
#include <stdbool.h>
#include <sys/types.h>
#include <sys/stat.h>
#endif

struct Path {
    int32_t dirfd_minus_at_fdcwd;
    const char* path; /* path valid if non-null */
    dev_t device_major;
    dev_t device_minor;
    ino_t inode;
    /* TODO: throw in mtime too. */
    /* struct statx_timestamp modification_time; */
    bool stat_valid;
    bool dirfd_valid;
};

static struct Path null_path = {-1, NULL, -1, -1, -1, false, false};
/* We don't need to free paths since I switched to the Arena allocator */
/* static void free_path(struct Path path); */

struct InitProcessOp {
    pid_t process_id;
    unsigned int exec_epoch;
    struct timespec process_birth_time;
    OWNED char* program_name;
};

struct InitProcessOp init_current_process();

struct InitThreadOp {
    pid_t process_id;
    struct timespec process_birth_time;
    unsigned int exec_epoch;
    pid_t sams_thread_id; /* Not the same as TID in Linux */
};

enum OpCode {
    FIRST_OP_CODE,
    init_process_op_code,
    init_thread_op_code,
    open_op_code,
    close_op_code,
    chdir_op_code,
    exec_op_code,
    clone_op_code,
    exit_op_code,
    access_op_code,
    stat_op_code,
    chown_op_code,
    chmod_op_code,
    read_link_op_code,
    LAST_OP_CODE,
};

struct OpenOp {
    struct Path path;
    int flags;
    mode_t mode;
    int32_t fd;
    int ferrno;
};

struct CloseOp {
    int32_t low_fd;
    int32_t high_fd;
    int ferrno;
};

struct ChdirOp {
    struct Path path;
    int ferrno;
};

struct ExecOp {
    struct Path path;
    int ferrno;
};

struct CloneOp {
    int flags;
    bool run_pthread_atfork_handlers;
    pid_t child_process_id;
    pid_t child_thread_id;
    int ferrno;
};

struct ExitOp {
    int status;
    bool run_atexit_handlers;
};

struct AccessOp {
    struct Path path;
    int mode;
    int flags;
    int ferrno;
};

struct StatOp {
    struct Path path;
    int flags;
    int mask;
    struct statx statx_buf;
    int ferrno;
};

struct ChownOp {
    struct Path path;
    uid_t uid;
    gid_t gid;
    int ferrno;
};

struct ChmodOp {
    struct Path path;
    mode_t mode;
    int ferrno;
};

struct ReadLinkOp {
    struct Path path;
    const char* resolved;
    int ferrno;
};

struct Op {
    enum OpCode op_code;
    union {
        struct InitProcessOp init_process;
        struct InitThreadOp init_thread;
        struct OpenOp open;
        struct CloseOp close;
        struct ChdirOp chdir;
        struct ExecOp exec;
        struct CloneOp clone;
        struct ExitOp exit;
        struct AccessOp access;
        struct StatOp stat;
        struct ChownOp chown;
        struct ChmodOp chmod;
        struct ReadLinkOp read_link;
    } data;
    struct timespec time;
};

/* We don't need this since we switched to an Arena allocator */
/* static void free_op(struct Op op); */
