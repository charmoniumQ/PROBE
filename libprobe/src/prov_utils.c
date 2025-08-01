#define _GNU_SOURCE

#include "prov_utils.h"

#include <fcntl.h>         // for O_CREAT, AT_FDCWD, O_RDWR
#include <limits.h>        // IWYU pragma: keep for PATH_MAX
#include <stdbool.h>       // for bool, true, false
#include <string.h>        // for strlen, strncpy
#include <sys/resource.h>  // IWYU pragma: keep for rusage
#include <sys/stat.h>      // IWYU pragma: keep for stat, statx, statx_timestamp
#include <sys/sysmacros.h> // for major, minor
#include <time.h>          // for timespec
// IWYU pragma: no_include "bits/types/struct_rusage.h"      for rusage, rusage::(anonymous)
// IWYU pragma: no_include "linux/limits.h"                  for PATH_MAX
// IWYU pragma: no_include "linux/stat.h"                    for statx, statx_timestamp

#include "../generated/libc_hooks.h"      // for unwrapped_statx
#include "../include/libprobe/prov_ops.h" // for OpCode, StatResult, Op
#include "arena.h"                        // for arena_strndup
#include "debug_logging.h"                // for DEBUG, EXPECT_NONNULL, NOT...
#include "global_state.h"                 // for get_data_arena, get_exec_e...
#include "prov_buffer.h"                  // for prov_log_record, prov_log_try
#include "util.h"                         // for CHECK_SNPRINTF, BORROWED

struct Path create_path_lazy(int dirfd, BORROWED const char* path, int flags) {
    if (LIKELY(prov_log_is_enabled())) {
        struct Path ret = {
            dirfd - AT_FDCWD,
            (path != NULL ? EXPECT_NONNULL(arena_strndup(get_data_arena(), path, PATH_MAX)) : NULL),
            -1,
            -1,
            -1,
            0,
            {0},
            {0},
            0,
            false,
            true,
        };

        /*
         * If path is empty string, AT_EMPTY_PATH should probably be set.
         * I can't think of a counterexample that isn't some kind of error.
         * However, some functions permit passing NULL.
         *
         * Then again, this could happen in the tracee's code too...
         * TODO: Remove this once I debug myself.
         * */
        //assert(path == NULL || (path[0] != '\0' || flags & AT_EMPTY_PATH));

        /*
         * if path == NULL, then the target is the dir specified by dirfd.
         * */
        struct statx statx_buf;
        int stat_ret = unwrapped_statx(dirfd, path, flags,
                                       STATX_TYPE | STATX_MODE | STATX_INO | STATX_MTIME |
                                           STATX_CTIME | STATX_SIZE,
                                       &statx_buf);
        if (stat_ret == 0) {
            ret.device_major = statx_buf.stx_dev_major;
            ret.device_minor = statx_buf.stx_dev_minor;
            ret.mode = statx_buf.stx_mode;
            ret.inode = statx_buf.stx_ino;
            ret.mtime = statx_buf.stx_mtime;
            ret.ctime = statx_buf.stx_ctime;
            ret.size = statx_buf.stx_size;
            ret.stat_valid = true;
        } else {
            DEBUG("Stat of %d,%s is not valid", dirfd, path);
        }
        return ret;
    } else {
        DEBUG("prov log not enabled");
        return null_path;
    }
}

void path_to_id_string(const struct Path* path, BORROWED char* string) {
    CHECK_SNPRINTF(
        string, PATH_MAX, "%04x-%04x-%016lx-%016lldx-%08x-%016lx", path->device_major,
        path->device_minor, path->inode,
        /* In GCC, this field is long int; in Clang, it is long long int. Always cast to the larger */
        (long long int)path->mtime.tv_sec, path->mtime.tv_nsec, path->size);
}

int fopen_to_flags(BORROWED const char* fopentype) {
    /* Table from fopen to open is documented here:
     * https://www.man7.org/linux/man-pages/man3/fopen.3.html
     **/
    bool plus = fopentype[1] == '+' || (fopentype[1] != '\0' && fopentype[2] == '+');
    if (fopentype[0] == 'r' && !plus) {
        return O_RDONLY;
    } else if (fopentype[0] == 'r' && plus) {
        return O_RDWR;
    } else if (fopentype[0] == 'w' && !plus) {
        return O_WRONLY | O_CREAT | O_TRUNC;
    } else if (fopentype[0] == 'w' && plus) {
        return O_RDWR | O_CREAT | O_TRUNC;
    } else if (fopentype[0] == 'a' && !plus) {
        return O_WRONLY | O_CREAT | O_APPEND;
    } else if (fopentype[0] == 'a' && plus) {
        return O_RDWR | O_CREAT | O_APPEND;
    } else {
        NOT_IMPLEMENTED("Unknown fopentype %s", fopentype);
    }
}

const struct Path* op_to_path(const struct Op* op) {
    switch (op->op_code) {
    case open_op_code:
        return &op->data.open.path;
    case chdir_op_code:
        return &op->data.chdir.path;
    case exec_op_code:
        return &op->data.exec.path;
    case init_exec_epoch_op_code:
        return &op->data.init_exec_epoch.exe;
    case access_op_code:
        return &op->data.access.path;
    case stat_op_code:
        return &op->data.stat.path;
    case update_metadata_op_code:
        return &op->data.update_metadata.path;
    case read_link_op_code:
        return &op->data.read_link.linkpath;
    case hard_link_op_code:
        return &op->data.hard_link.old;
    case symbolic_link_op_code:
        return &op->data.symbolic_link.new;
    case unlink_op_code:
        return &op->data.unlink.path;
    case rename_op_code:
        return &op->data.rename.src;
    case mkfile_op_code:
        return &op->data.mkfile.path;
    case readdir_op_code:
        return &op->data.readdir.dir;
    default:
        return &null_path;
    }
}
const struct Path* op_to_second_path(const struct Op* op) {
    switch (op->op_code) {
    case hard_link_op_code:
        return &op->data.hard_link.new;
    case rename_op_code:
        return &op->data.rename.dst;
    default:
        return &null_path;
    }
}

BORROWED const char* op_code_to_string(enum OpCode op_code) {
    switch (op_code) {
    case init_exec_epoch_op_code:
        return "init_exec_epoch";
    case init_thread_op_code:
        return "init_thread";
    case open_op_code:
        return "open";
    case close_op_code:
        return "close";
    case clone_op_code:
        return "clone";
    case chdir_op_code:
        return "chdir";
    case exec_op_code:
        return "exec";
    case spawn_op_code:
        return "spawn";
    case exit_op_code:
        return "exit";
    case access_op_code:
        return "access";
    case stat_op_code:
        return "stat";
    case readdir_op_code:
        return "readdir";
    case wait_op_code:
        return "wait";
    case update_metadata_op_code:
        return "update_metadata";
    case read_link_op_code:
        return "readlink";
    case dup_op_code:
        return "dup";
    case hard_link_op_code:
        return "hard_link";
    case symbolic_link_op_code:
        return "symbolic_link";
    case unlink_op_code:
        return "unlink";
    case rename_op_code:
        return "rename";
    case mkfile_op_code:
        return "mkfile";
    default:
        ASSERTF(FIRST_OP_CODE < op_code && op_code < LAST_OP_CODE, "Not a valid op_code: %d",
                op_code);
        NOT_IMPLEMENTED("op_code %d is valid, but not handled", op_code);
    }
}
int path_to_string(const struct Path* path, char* buffer, int buffer_length) {
    return CHECK_SNPRINTF(
        buffer, buffer_length, "dirfd=%d, path=\"%s\", stat_valid=%d, dirfd_valid=%d",
        path->dirfd_minus_at_fdcwd + AT_FDCWD, path->path, path->stat_valid, path->dirfd_valid);
}
void op_to_human_readable(char* dest, int size, struct Op* op) {
    const char* op_str = op_code_to_string(op->op_code);
    strncpy(dest, op_str, size);
    size -= strlen(op_str);
    dest += strlen(op_str);

    dest[0] = ' ';
    dest++;
    size--;

    const struct Path* path = op_to_path(op);
    if (path->dirfd_valid) {
        int path_size = path_to_string(path, dest, size);
        dest += path_size;
        size -= path_size;
    }

    if (op->op_code == open_op_code) {
        int fd_size =
            CHECK_SNPRINTF(dest, size, " fd=%d flags=%d", op->data.open.fd, op->data.open.flags);
        dest += fd_size;
        size -= fd_size;
    }

    if (op->op_code == init_exec_epoch_op_code) {
        int fd_size =
            CHECK_SNPRINTF(dest, size, " pid=%d parent_pid=%d", op->data.init_exec_epoch.pid,
                           op->data.init_exec_epoch.parent_pid);
        dest += fd_size;
        size -= fd_size;
    }

    if (op->op_code == close_op_code) {
        int fd_size = CHECK_SNPRINTF(dest, size, " fd=%d", op->data.close.fd);
        dest += fd_size;
        size -= fd_size;
    }
    (void)dest;
    (void)size;
}

void stat_result_from_stat(struct StatResult* stat_result_buf, struct stat* stat_buf) {
    stat_result_buf->mask = STATX_BASIC_STATS;
    stat_result_buf->mode = stat_buf->st_mode;
    stat_result_buf->ino = stat_buf->st_ino;
    stat_result_buf->dev_major = major(stat_buf->st_dev);
    stat_result_buf->dev_major = minor(stat_buf->st_dev);
    stat_result_buf->nlink = stat_buf->st_nlink;
    stat_result_buf->uid = stat_buf->st_uid;
    stat_result_buf->gid = stat_buf->st_gid;
    stat_result_buf->size = stat_buf->st_size;
    stat_result_buf->atime.tv_sec = stat_buf->st_atim.tv_sec;
    stat_result_buf->atime.tv_nsec = stat_buf->st_atim.tv_nsec;
    stat_result_buf->mtime.tv_sec = stat_buf->st_mtim.tv_sec;
    stat_result_buf->mtime.tv_nsec = stat_buf->st_mtim.tv_nsec;
    stat_result_buf->ctime.tv_sec = stat_buf->st_ctim.tv_sec;
    stat_result_buf->ctime.tv_nsec = stat_buf->st_ctim.tv_nsec;
    stat_result_buf->blocks = stat_buf->st_blocks;
    stat_result_buf->blksize = stat_buf->st_blksize;
}

void stat_result_from_statx(struct StatResult* stat_result_buf, struct statx* statx_buf) {
    stat_result_buf->mask = statx_buf->stx_mask;
    stat_result_buf->mode = statx_buf->stx_mode;
    stat_result_buf->ino = statx_buf->stx_ino;
    stat_result_buf->dev_major = statx_buf->stx_dev_major;
    stat_result_buf->dev_major = statx_buf->stx_dev_minor;
    stat_result_buf->nlink = statx_buf->stx_nlink;
    stat_result_buf->uid = statx_buf->stx_uid;
    stat_result_buf->gid = statx_buf->stx_gid;
    stat_result_buf->size = statx_buf->stx_size;
    stat_result_buf->atime.tv_sec = statx_buf->stx_atime.tv_sec;
    stat_result_buf->atime.tv_nsec = statx_buf->stx_atime.tv_nsec;
    stat_result_buf->mtime.tv_sec = statx_buf->stx_mtime.tv_sec;
    stat_result_buf->mtime.tv_nsec = statx_buf->stx_mtime.tv_nsec;
    stat_result_buf->ctime.tv_sec = statx_buf->stx_ctime.tv_sec;
    stat_result_buf->ctime.tv_nsec = statx_buf->stx_ctime.tv_nsec;
    stat_result_buf->blocks = statx_buf->stx_blocks;
    stat_result_buf->blksize = statx_buf->stx_blksize;
}

/* TODO: Use the Musl rusage as the source-of-truth, and we will all be good to memcpy */

void copy_rusage(struct my_rusage* dst, struct rusage* src) {
    dst->ru_utime = src->ru_utime;
    dst->ru_stime = src->ru_stime;
    dst->ru_maxrss = src->ru_maxrss;
    dst->ru_ixrss = src->ru_ixrss;
    dst->ru_idrss = src->ru_idrss;
    dst->ru_isrss = src->ru_isrss;
    dst->ru_minflt = src->ru_minflt;
    dst->ru_majflt = src->ru_majflt;
    dst->ru_nswap = src->ru_nswap;
    dst->ru_inblock = src->ru_inblock;
    dst->ru_oublock = src->ru_oublock;
    dst->ru_msgsnd = src->ru_msgsnd;
    dst->ru_msgrcv = src->ru_msgrcv;
    dst->ru_nsignals = src->ru_nsignals;
    dst->ru_nvcsw = src->ru_nvcsw;
    dst->ru_nivcsw = src->ru_nivcsw;
}
