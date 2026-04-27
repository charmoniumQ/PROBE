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
#include "debug_logging.h"        // for DEBUG, EXPECT_NONNULL, NOT...
#include "probe_libc.h"           // for probe_libc_strlen
#include "util.h"                 // for CHECK_SNPRINTF, BORROWED

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
    default:
        return "UnknownOp";
    }
}

static const size_t MAX_OPCODE_STRING_LENGTH = 256;

void op_to_human_readable(char* dest, int size, struct Op* op) {
    const char* op_str = op_code_to_string(op->data.tag);
    probe_libc_strncpy(dest, op_str, size);
    size -= probe_libc_strnlen(op_str, MAX_OPCODE_STRING_LENGTH);
    dest += probe_libc_strnlen(op_str, MAX_OPCODE_STRING_LENGTH);

    dest[0] = ' ';
    dest++;
    size--;

    switch (op->data.tag) {
    case OpData_Open: {
        int fd_size = CHECK_SNPRINTF(dest, size, " flags=%d", op->data.open.flags);
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
        int fd_size = CHECK_SNPRINTF(dest, size, " fd=%d ", op->data.close.open_number.value);
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
