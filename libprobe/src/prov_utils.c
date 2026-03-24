#define _GNU_SOURCE

#include "prov_utils.h"

#include <fcntl.h>         // for O_CREAT, AT_FDCWD, O_RDWR
#include <limits.h>        // IWYU pragma: keep for PATH_MAX
#include <stdbool.h>       // for bool, true, false
#include <sys/resource.h>  // IWYU pragma: keep for rusage
#include <sys/stat.h>      // IWYU pragma: keep for stat, statx, statx_timestamp
#include <sys/sysmacros.h> // for major, minor
#include <time.h>          // for timespec
// IWYU pragma: no_include "bits/types/struct_rusage.h"      for rusage, rusage::(anonymous)
// IWYU pragma: no_include "linux/limits.h"                  for PATH_MAX
// IWYU pragma: no_include "linux/stat.h"                    for statx, statx_timestamp

#include "../generated/headers.h" // for OpCode, StatResult, Op
#include "arena.h"                // for arena_strndup
#include "debug_logging.h"        // for DEBUG, EXPECT_NONNULL, NOT...
#include "global_state.h"         // for get_data_arena, get_exec_e...
#include "probe_libc.h"           // for probe_libc_strlen
#include "util.h"                 // for CHECK_SNPRINTF, BORROWED

static const struct Path null_path = {0, NULL, 0, 0, 0, 0, {0}, {0}, 0, false};

struct Path create_path_lazy(int dirfd, BORROWED const char* path, int fd, int flags) {
    ASSERTF((path && dirfd != -1) || (!path && (dirfd == -1 || (flags & AT_EMPTY_PATH))),
            "Either dirfd and path are both set, both unset, or AT_EMPTY_PATH: %d %s %d", dirfd,
            path, fd);
    ASSERTF(dirfd != 0 || (path && path[0] == '/'), "dirfd==0 implies absolute path: %d %s %d",
            dirfd, path, fd);
    struct Path ret = {
        dirfd,
        (path != NULL ? EXPECT_NONNULL(arena_strndup(get_data_arena(), path, PATH_MAX)) : NULL),
        -1,
        -1,
        -1,
        0,
        {0},
        {0},
        0,
        false,
    };

    struct statx statx_buf;
    result stat_ret;
    if (fd != -1) {
        stat_ret = probe_libc_statx(fd, NULL, flags | AT_EMPTY_PATH,
                                    STATX_TYPE | STATX_MODE | STATX_INO | STATX_MTIME |
                                        STATX_CTIME | STATX_SIZE,
                                    &statx_buf);
        if (stat_ret != 0) {
            WARNING("We got a bad FD; could be the client's fault? fd=%d stat_ret=%d", fd,
                    stat_ret);
        }
    } else {
        stat_ret = probe_libc_statx(dirfd, path, flags,
                                    STATX_TYPE | STATX_MODE | STATX_INO | STATX_MTIME |
                                        STATX_CTIME | STATX_SIZE,
                                    &statx_buf);
    }
    if (stat_ret == 0) {
        ret.device_major = statx_buf.stx_dev_major;
        ret.device_minor = statx_buf.stx_dev_minor;
        ret.mode = statx_buf.stx_mode;
        ret.inode = statx_buf.stx_ino;
        ret.mtime = *(struct StatxTimestamp*)&statx_buf.stx_mtime;
        ret.ctime = *(struct StatxTimestamp*)&statx_buf.stx_ctime;
        ret.size = statx_buf.stx_size;
        ret.stat_valid = true;
    } else {
        /* DEBUG("Stat of %d,%s is not valid", dirfd, path); */
    }
    return ret;
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
    switch (op->data.tag) {
    case OpData_Open:
        return &op->data.open.path;
    case OpData_Chdir:
        return &op->data.chdir.path;
    case OpData_Exec:
        return &op->data.exec.path;
    case OpData_InitExecEpoch:
        return &op->data.init_exec_epoch.exe;
    case OpData_Access:
        return &op->data.access.path;
    case OpData_Stat:
        return &op->data.stat.path;
    case OpData_UpdateMetadata:
        return &op->data.update_metadata.path;
    case OpData_ReadLink:
        return &op->data.read_link.linkpath;
    case OpData_HardLink:
        return &op->data.hard_link.old;
    case OpData_SymbolicLink:
        return &op->data.symbolic_link.new_;
    case OpData_Unlink:
        return &op->data.unlink.path;
    case OpData_Rename:
        return &op->data.rename.src;
    case OpData_MkFile:
        return &op->data.mk_file.path;
    case OpData_Readdir:
        return &op->data.readdir.dir;
    default:
        return &null_path;
    }
}
const struct Path* op_to_second_path(const struct Op* op) {
    switch (op->data.tag) {
    case OpData_HardLink:
        return &op->data.hard_link.new_;
    case OpData_Rename:
        return &op->data.rename.dst;
    default:
        return &null_path;
    }
}

BORROWED const char* op_code_to_string(enum OpData_Tag op_code) {
    switch (op_code) {
    case OpData_InitExecEpoch:
        return "InitExecEpoch";
    case OpData_InitThread:
        return "InitThread";
    case OpData_Open:
        return "Open";
    case OpData_Close:
        return "Close";
    case OpData_Chdir:
        return "Chdir";
    case OpData_Exec:
        return "Exec";
    case OpData_Spawn:
        return "Spawn";
    case OpData_Clone:
        return "Clone";
    case OpData_ExitThread:
        return "ExitThread";
    case OpData_ExitProcess:
        return "ExitProcess";
    case OpData_Access:
        return "Access";
    case OpData_Stat:
        return "Stat";
    case OpData_Readdir:
        return "Readdir";
    case OpData_Wait:
        return "Wait";
    case OpData_UpdateMetadata:
        return "UpdateMetadata";
    case OpData_ReadLink:
        return "ReadLink";
    case OpData_Dup:
        return "Dup";
    case OpData_HardLink:
        return "HardLink";
    case OpData_SymbolicLink:
        return "SymbolicLink";
    case OpData_Unlink:
        return "Unlink";
    case OpData_Rename:
        return "Rename";
    case OpData_MkFile:
        return "MkFile";
    default:
        return "UnknownOp";
    }
}

static const size_t MAX_OPCODE_STRING_LENGTH = 256;

int path_to_string(const struct Path* path, char* buffer, int buffer_length) {
    return CHECK_SNPRINTF(buffer, buffer_length, "%s", path->path);
}
void op_to_human_readable(char* dest, int size, struct Op* op) {
    const char* op_str = op_code_to_string(op->data.tag);
    probe_libc_strncpy(dest, op_str, size);
    size -= probe_libc_strnlen(op_str, MAX_OPCODE_STRING_LENGTH);
    dest += probe_libc_strnlen(op_str, MAX_OPCODE_STRING_LENGTH);

    dest[0] = ' ';
    dest++;
    size--;

    const struct Path* path = op_to_path(op);
    if (path->dirfd != -1) {
        int path_size = path_to_string(path, dest, size);
        dest += path_size;
        size -= path_size;
    }

    switch (op->data.tag) {
    case OpData_Open: {
        int fd_size =
            CHECK_SNPRINTF(dest, size, " fd=%d flags=%d", op->data.open.fd, op->data.open.flags);
        dest += fd_size;
        size -= fd_size;
        break;
    }
    case OpData_InitExecEpoch: {
        int fd_size =
            CHECK_SNPRINTF(dest, size, " pid=%d parent_pid=%d ", op->data.init_exec_epoch.pid,
                           op->data.init_exec_epoch.parent_pid);
        dest += fd_size;
        size -= fd_size;
        break;
    }
    case OpData_Close: {
        int fd_size = CHECK_SNPRINTF(dest, size, " fd=%d ", op->data.close.fd);
        dest += fd_size;
        size -= fd_size;
        break;
    }
    case OpData_Clone: {
        int task_size = CHECK_SNPRINTF(dest, size, " task_type=%d task_id=%ld",
                                       op->data.clone.task_type, op->data.clone.task_id);
        dest += task_size;
        size -= task_size;
        break;
    }
    case OpData_Wait: {
        int task_size = CHECK_SNPRINTF(dest, size, " task_type=%d task_id=%ld",
                                       op->data.clone.task_type, op->data.clone.task_id);
        dest += task_size;
        size -= task_size;
        break;
    }
    default: {
    }
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
