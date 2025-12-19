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

#include "../include/libprobe/prov_ops.h" // for OpCode, StatResult, Op
#include "arena.h"                        // for arena_strndup
#include "debug_logging.h"                // for DEBUG, EXPECT_NONNULL, NOT...
#include "global_state.h"                 // for get_data_arena, get_exec_e...
#include "probe_libc.h"                   // for probe_libc_strlen
#include "prov_buffer.h"                  // for prov_log_record, prov_log_try
#include "util.h"                         // for CHECK_SNPRINTF, BORROWED

struct OpenNumbering _open_numbering;
_Atomic(OpenNumber) _unused_open_number = 1;

struct Path2 to_path(int dirfd, const char* filename, size_t length) {
    return (struct Path2) {
        .dirfd_minus_at_fdcwd = dirfd - AT_FDCWD,
        .dirfd_open_number = open_numbering_address_of(_open_numbering, dirfd - AT_FDCWD),
        .path = filename ? arena_strndup(get_data_arena(), filename, length ? length : PATH_MAX) : NULL;
    }
}

OpenNumber open_numbering_new(int fd) {
    OpenNumber new = atomic_fetch_add(&unused_open_number, 1);
    ASSERTF(new < (1L << 16) - 10, "Awfully close to the largest possible open-number. Consider resizing");
    OpenNumber old = atomic_exchange(open_numbering_address_of_strong(&open_numbering, fd - AT_FDCWD), open_number);
    if (old) {
        WARNING("Open returned fd=%d, but fd=%d is already occupied by open_number=%d", fd, fd, old);
    }
}

OpenNumber open_numbering_close(int fd) {
    return atomic_exchange(open_numbering_address_of_strong(&open_numbering, fd - AT_FDCWD), 0);
}

OpenNumber open_numbering_dup(int oldfd, int newfd, OpenNumber* closed_dest) {
    OpenNumber dupped = atomic_load(open_numbering_address_of_strong(&open_numbering, old - AT_FDCWD));
    OpenNumber closed = atomic_exchange(open_numbering_address_of_strong(&open_numbering, ret - AT_FDCWD), dupped);
    if (closed) {
        if (closed_dest) {
            *closed_fd = closed;
        } else {
            ERROR("Dup returned fd=%d, but fd=%d is already occupied by open_number=%d", newfd, newfd, closed);
        }
    }
    return dupped;
}

void path_to_id_string(const struct Path* path, BORROWED char* string) {
    CHECK_SNPRINTF(
        string, PATH_MAX, "%04x-%04x-%016lx-%016lldx-%08x-%016lx", path->device_major,
        path->device_minor, path->inode,
        /* In GCC, this field is long int; in Clang, it is long long int. Always cast to the larger */
        (long long int)path->mtime.tv_sec, path->mtime.tv_nsec, path->size);
}

struct StatxTruncated my_fstat(int fd, int stat_flags) {
    struct statx statx_buf;
    int ret = statx(fd, "", AT_EMPTY_PATH, STATX_INO | STATX_TYPE | STATX_MTIME, &statx_buf);
    if (UNLIKELY(ret != 0)) {
        statx_buf.stx_ino = 0;
    }
    return *(struct StatResult&)&statx_buf;
}

struct StatxTruncated copy_if_necessary(int fd, int open_flags) {
    enum CopyFiles mode = get_copy_files_mode();
    struct statx statx_buf = my_fstat(fd, 0);
    enum Access access = UNKNOWN_ACCESS;
    if ((op.data.open.flags & O_ACCMODE) == O_RDONLY) {
        access = READ_ACCESS;
    } else if (op.data.open.flags & (O_TRUNC | O_CREAT)) {
        access = TRUNCATE_WRITE_ACCESS;
    } else if ((op.data.open.flags & O_ACCMODE) == O_WRONLY) {
        access = WRITE_ACCESS;
    } else if ((op.data.open.flags & O_ACCMODE) == O_RDWR) {
        access = READ_WRITE_ACCESS;
    } else {
        ERROR("unreachable code, %d %08x", fd, flags);
    }
    if ((mode == CopyFiles_Lazily || mode == CopyFiles_Eagerly) && ret == 0) {
        struct InodeTable* read_inodes = get_read_inodes();
        struct InodeTable* coo_inodes = get_copied_or_overwritten_inodes();

        ASSERTF(statx_buf.stx_dev_major < 256,
                "Unexpectedly large device major number, %d. Resize inode table levels",
                statx_buf.stx_dev_major);
        ASSERTF(statx_buf.stx_dev_minor < 256,
                "Unexpectedly large device minor number, %d. Resize inode table levels",
                statx_buf.stx_dev_minor);
        ASSERTF(path->inode <= (1L << 32), "Unexpectedly large inode, %d. Resize inode table levels", statx_buf.stx_ino);
        uint64_t index = (((uint64_t)(statx_buf.stx_dev_major)) << 48L) |
                         (((uint64_t)(statx_buf.stx_dev_minor)) << 32L) |
                         statx_buf.stx_ino;

        if (mode == CopyFiles_Lazily) {
            if (access == READ_ACCESS) {
                DEBUG("Reading %d %08lx", fd, statx_buf.stx_ino);
                _Atomic(bool)* _Nonnull read_loc = inode_table_address_of_strong(read_inodes, index);
                atomic_store(read_loc, true);
            } else if (access == READ_WRITE_ACCESS || access == WRITE_ACCESS) {
                _Atomic(bool)* _Nonnull coo_loc = inode_table_address_of_strong(coo_inodes, index);
                if (atomic_exchange(coo_loc, true)) {
                    DEBUG("Mutating, but not copying %d %08lx since it is copied already or "
                          "overwritten",
                          fd, statx_buf.stx_ino);
                } else {
                    DEBUG("Mutating, therefore copying %d %08lx", fd, statx_buf.stx_ino);
                    if (copy_to_store(path) != 0) {
                        ERROR("Copying failed");
                    }
                }
            } else if (access == TRUNCATE_WRITE_ACCESS) {
                _Atomic(bool)* _Nonnull read_loc = inode_table_address_of_strong(read_inodes, index);
                if (atomic_load(read_loc)) {
                    _Atomic(bool)* _Nonnull coo_loc = inode_table_address_of_strong(coo_inodes, index);
                    if (atomic_exchange(coo_loc, true)) {
                        DEBUG("Mutating, but not copying %d %08lx since it is copied already or "
                              "overwritten", fd, statx_buf.stx_ino);
                    } else {
                        DEBUG("Replace after read %d %08lx", fd, statx_buf.stx_ino);
                        if (copy_to_store(path) != 0) {
                            ERROR("Copying failed");
                        }
                    }
                } else {
                    DEBUG("Mutating, but not copying %d %08lx since it was never read", fd, statx_buf.stx_ino);
                }
            }
        } else if (access == READ_ACCESS || access == READ_WRITE_ACCESS || access == WRITE_ACCESS) {
            ASSERTF(mode == CopyFiles_Eagerly, "");
            _Atomic(bool)* _Nonnull coo_loc = inode_table_address_of_strong(coo_inodes, index);
            if (atomic_exchange(coo_loc, true)) {
                DEBUG("Not copying %d %08lx because already did", fd, statx_buf.stx_ino);
            } else {
                if (copy_to_store(path) != 0) {
                    ERROR("Copying failed");
                }
            }
        }
    }
    if (flags & O_TRUNC) {
        int ret2 = ftruncate(fd, 0);
        if (UNLIKELY(ret2 != 0)) {
            ERROR("Open succeeded, but truncate failed");
        }
    }
    return statx_buf;
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
    case exit_thread_op_code:
        return "exit_thread";
    case exit_process_op_code:
        return "exit_process";
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

static const size_t MAX_OPCODE_STRING_LENGTH = 256;

int path_to_string(const struct Path* path, char* buffer, int buffer_length) {
    return CHECK_SNPRINTF(buffer, buffer_length, "%s", path->path);
}
void op_to_human_readable(char* dest, int size, struct Op* op) {
    const char* op_str = op_code_to_string(op->op_code);
    probe_libc_strncpy(dest, op_str, size);
    size -= probe_libc_strnlen(op_str, MAX_OPCODE_STRING_LENGTH);
    dest += probe_libc_strnlen(op_str, MAX_OPCODE_STRING_LENGTH);

    dest[0] = ' ';
    dest++;
    size--;

    const struct Path* path = op_to_path(op);
    if (path->dirfd_minus_at_fdcwd + AT_FDCWD != -1) {
        int path_size = path_to_string(path, dest, size);
        dest += path_size;
        size -= path_size;
    }

    if (op->op_code == open_op_code) {
        int fd_size =
            CHECK_SNPRINTF(dest, size, " fd=%d flags=%d", op->data.open.fd, op->data.open.flags);
        dest += fd_size;
        size -= fd_size;
    } else if (op->op_code == init_exec_epoch_op_code) {
        int fd_size =
            CHECK_SNPRINTF(dest, size, " pid=%d parent_pid=%d ", op->data.init_exec_epoch.pid,
                           op->data.init_exec_epoch.parent_pid);
        dest += fd_size;
        size -= fd_size;
    } else if (op->op_code == close_op_code) {
        int fd_size = CHECK_SNPRINTF(dest, size, " fd=%d ", op->data.close.fd);
        dest += fd_size;
        size -= fd_size;
    } else if (op->op_code == clone_op_code) {
        int task_size = CHECK_SNPRINTF(dest, size, " task_type=%d task_id=%ld",
                                       op->data.clone.task_type, op->data.clone.task_id);
        dest += task_size;
        size -= task_size;
    } else if (op->op_code == wait_op_code) {
        int task_size = CHECK_SNPRINTF(dest, size, " task_type=%d task_id=%ld",
                                       op->data.clone.task_type, op->data.clone.task_id);
        dest += task_size;
        size -= task_size;
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
