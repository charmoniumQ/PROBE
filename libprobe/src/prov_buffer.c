#include "prov_buffer.h"

#include <fcntl.h>  // for AT_FDCWD, O_RDWR, O_CREAT
#include <limits.h> // IWYU pragma: keep for PATH_MAX
#include <stdatomic.h>
#include <stdbool.h> // for bool, true
#include <stdint.h>
#include <sys/stat.h> // for S_IFMT, S_IFCHR, S_IFDIR
#include <threads.h>  // for thrd_current
#include <time.h>     // IWYU pragma: keep for timespec, clock_gettime
#include <unistd.h>   // for F_OK
// IWYU pragma: no_include "bits/time.h"    for CLOCK_MONOTONIC
// IWYU pragma: no_include "linux/limits.h" for PATH_MAX

#include "../generated/fd_table.h"    // for fd_table_address_of_strong
#include "../generated/headers.h"     // for Inode, OpenNumber, Op, OpData_Tag
#include "../generated/inode_table.h" // for inode_table_address_of_strong
#include "../generated/libc_hooks.h"  // for client_fopen, client_openat
#include "arena.h"                    // for arena_strndup, arena_sync, are...
#include "debug_logging.h"            // for DEBUG, ERROR, ASSERTF
#include "errno.h"                    // for errno
#include "global_state.h"             // for get_data_arena, get_op_arena
#include "linux/stat.h"               // for statx, STATX_CTIME, STATX_INO
#include "probe_libc.h"               // for probe_copy_file, probe_libc_fa...
#include "stdio.h"                    // for fileno
#include "util.h"                     // for BORROWED, CHECK_SNPRINTF

void prov_log_save() {
    /* TODO: ensure we call Arena save in atexit, pthread_cleanup_push */
    DEBUG("prov log save");
    arena_sync(get_op_arena());
    arena_sync(get_data_arena());
}

enum AccessType {
    READ_ACCESS,
    TRUNCATE_WRITE_ACCESS,
    WRITE_ACCESS,
    READ_WRITE_ACCESS,
    UNKNOWN_ACCESS,
};

static inline void path_to_id_string(const struct Inode inode, BORROWED char* string) {
    CHECK_SNPRINTF(
        string, PATH_MAX, "%04x-%04x-%016lx-%016lldx-%08x-%016lx", inode.device_major,
        inode.device_minor, inode.inode,
        /* In GCC, this field is long int; in Clang, it is long long int. Always cast to the larger */
        (long long int)inode.mtime.tv_sec, inode.mtime.tv_nsec, inode.size);
}

static int copy_to_store(int fd, struct Inode inode) {
    static thread_local struct FixedPath store_path;
    static thread_local bool initialized = false;
    if (!initialized) {
        store_path = *get_probe_dir();
        initialized = true;
    }
    store_path.bytes[store_path.len] = '/';
    path_to_id_string(inode, store_path.bytes + store_path.len + 1);
    /*
    ** We take precautions to avoid calling copy(f) if copy(f) is already called in the same process.
    ** But it may have been already called in a different process!
    ** Especially coreutils used in every script.
     */
    result access = probe_libc_faccessat(AT_FDCWD, store_path.bytes, F_OK);
    if (access == 0) {
        return 0;
    } else if ((inode.mode & S_IFMT) == S_IFDIR) {
        ERROR("Can't copy directory %ld", inode.inode);
        // TODO: implement this
        // We need to copy the inode metadata (not actual contents) linked in this directory
        return 0;
    } else if ((inode.mode & S_IFMT) == S_IFREG) {
        DEBUG("Copying regular file %ld", inode.inode);
        return (int)probe_copy_file(fd, AT_FDCWD, store_path.bytes, inode.size);
    } else if ((inode.mode & S_IFMT) == S_IFCHR) {
        DEBUG("Copying block device file %ld", inode.inode);
        // TODO
        return 0;
    } else {
        ERROR("Not sure how to copy special file inode=%ld, (mode & S_IFMT)=%d", inode.inode,
              inode.mode & S_IFMT);
        return 0;
    }
}

static struct InodeTable read_inodes;
static struct InodeTable copied_or_overwritten_inodes;

static void maybe_copy_to_store(enum AccessType access, int fd, struct Inode inode) {
    enum CopyFiles mode = get_copy_files_mode();
    if ((mode == CopyFiles_Lazily || mode == CopyFiles_Eagerly)) {
        ASSERTF(inode.device_major < 256,
                "Unexpectedly large device major number, %d. Resize inode table levels",
                inode.device_major);
        ASSERTF(inode.device_minor < 256,
                "Unexpectedly large device minor number, %d. Resize inode table levels",
                inode.device_minor);
        ASSERTF(inode.inode <= (1L << 32),
                "Unexpectedly large inode, %lu. Resize inode table levels", inode.inode);
        uint64_t index = (((uint64_t)(inode.device_major)) << 48L) |
                         (((uint64_t)(inode.device_minor)) << 32L) | inode.inode;
        if (mode == CopyFiles_Lazily) {
            if (access == READ_ACCESS) {
                DEBUG("Reading %ld", inode.inode);
                _Atomic(bool)* _Nonnull read_loc =
                    inode_table_address_of_strong(&read_inodes, index);
                atomic_store(read_loc, true);
            } else if (access == READ_WRITE_ACCESS || access == WRITE_ACCESS) {
                _Atomic(bool)* _Nonnull coo_loc =
                    inode_table_address_of_strong(&copied_or_overwritten_inodes, index);
                if (atomic_exchange(coo_loc, true)) {
                    DEBUG("Mutating, but not copying %ld since it is copied already or "
                          "overwritten",
                          inode.inode);
                } else {
                    DEBUG("Mutating, therefore copying %ld", inode.inode);
                    if (copy_to_store(fd, inode) != 0) {
                        ERROR("Copying failed");
                    }
                }
            } else if (access == TRUNCATE_WRITE_ACCESS) {
                const _Atomic(bool)* _Nullable read_loc =
                    inode_table_address_of_weak(&read_inodes, index);
                if (read_loc && atomic_load(read_loc)) {
                    _Atomic(bool)* _Nonnull coo_loc =
                        inode_table_address_of_strong(&copied_or_overwritten_inodes, index);
                    if (atomic_exchange(coo_loc, true)) {
                        DEBUG("Mutating, but not copying %ld since it is copied already or "
                              "overwritten",
                              inode.inode);
                    } else {
                        DEBUG("Replace after read %ld", inode.inode);
                        if (copy_to_store(fd, inode) != 0) {
                            ERROR("Copying failed");
                        }
                    }
                } else {
                    DEBUG("Mutating, but not copying %ld since it was never read", inode.inode);
                }
            }
        } else if (access == READ_ACCESS || access == READ_WRITE_ACCESS || access == WRITE_ACCESS) {
            ASSERTF(mode == CopyFiles_Eagerly, "");
            _Atomic(bool)* _Nonnull coo_loc =
                inode_table_address_of_strong(&copied_or_overwritten_inodes, index);
            if (atomic_exchange(coo_loc, true)) {
                DEBUG("Not copying %ld because already did", inode.inode);
            } else {
                if (copy_to_store(fd, inode) != 0) {
                    ERROR("Copying failed");
                }
            }
        }
    }
}

struct Inode get_inode(int fd) {
    struct statx statx_buf;
    int stat_ret = probe_libc_statx(
        fd, NULL, 0 | AT_EMPTY_PATH,
        STATX_TYPE | STATX_MODE | STATX_INO | STATX_MTIME | STATX_CTIME | STATX_SIZE, &statx_buf);
    if (stat_ret != 0) {
        ERROR("We got a bad FD; could be the client's fault? fd=%d stat_ret=%d", fd, stat_ret);
    }
    return (struct Inode){
        .device_major = statx_buf.stx_dev_major,
        .device_minor = statx_buf.stx_dev_minor,
        .inode = statx_buf.stx_ino,
        .mode = statx_buf.stx_mode,
        .mtime = *(struct StatxTimestamp*)&statx_buf.stx_mtime,
        .ctime = *(struct StatxTimestamp*)&statx_buf.stx_ctime,
        .size = statx_buf.stx_size,
    };
}

static struct FdTable fd_table;

OpenNumber get_open_number(int fd) {
    return (OpenNumber){atomic_load(fd_table_address_of_strong(&fd_table, fd))};
}

OpenNumber reset_open_number(int fd) {
    return (OpenNumber){atomic_exchange(fd_table_address_of_strong(&fd_table, fd), 0)};
}

void set_open_number(int fd, OpenNumber open_no) {
    atomic_store(fd_table_address_of_strong(&fd_table, fd), open_no.value);
}

OpenNumber dup_open_numbers(int old, int new) {
    OpenNumber ret = get_open_number(old);
    set_open_number(new, ret);
    return ret;
}

_Atomic(uint16_t) unused_open_number = 1;

OpenNumber new_open_number(int fd) {
    OpenNumber ret = {atomic_fetch_add(&unused_open_number, 1)};
    set_open_number(fd, ret);
    return ret;
}

int open_wrapper(int dirfd, const char* filename, int flags, mode_t mode) {
    enum AccessType access;
    if ((flags & O_ACCMODE) == O_RDONLY) {
        access = READ_ACCESS;
    } else if (flags & (O_TRUNC | O_CREAT)) {
        access = TRUNCATE_WRITE_ACCESS;
    } else if ((flags & O_ACCMODE) == O_WRONLY) {
        access = WRITE_ACCESS;
    } else if ((flags & O_ACCMODE) == O_RDWR) {
        access = READ_WRITE_ACCESS;
    } else {
        ERROR("unreachable code, (flags & O_ACCMODE)=0x%x", flags & O_ACCMODE);
    }

    DEBUG("open_wrapper(%d, \"%s\", %d, %d), access=%d", dirfd, filename, flags, mode, access);

    int nondestructive_flags = (flags & ~(O_CREAT | O_TRUNC | O_TMPFILE)) | O_RDONLY;
    int saved_errno = 0;
    int fd = client_openat(dirfd, filename, nondestructive_flags, mode);
    struct Inode inode;
    if (fd >= 0) {
        inode = get_inode(fd);
        maybe_copy_to_store(access, fd, inode);
    } else {
        saved_errno = errno;
        // TODO: note the fact that the file did NOT exist
    }

    // TODO: If failed in a way that destructively-open would not fix, add op and leave

    if (flags != nondestructive_flags) {
        if (fd >= 0) {
            DEBUG("Closing the RW version");
            close(fd);
        }
        // TODO: try interpreting flags instead of doing close+open
        fd = client_openat(dirfd, filename, flags, mode);
        if (fd >= 0) {
            inode = get_inode(fd);
        } else {
            saved_errno = errno;
        }
    }

    OpenNumber open_number = {0};
    if (fd >= 0) {
        new_open_number(fd);
    }
    prov_log_record((struct Op){
        .data =
            {
                .open_tag = OpData_Open,
                .open =
                    {
                        .path =
                            {
                                .directory = get_open_number(dirfd),
                                .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                            },
                        .open_number = open_number,
                        .inode = inode,
                        .flags = flags,
                        .mode = mode,
                        .dir = false,
                        .creat =
                            false, /* This is only used when we _know_ that the file was created, like in pipe() */
                    },
            },
        .ferrno = 0,
    });
    if (fd < 0) {
        errno = saved_errno;
    } else {
        errno = 0;
    }
    return fd;
}

FILE* fopen_wrapper(const char* filename, const char* opentype) {
    DEBUG("fopen_wrapper(\"%s\", \"%s\")", filename, opentype);
    enum AccessType access;
    switch (opentype[0]) {
    case 'r':
        access = READ_ACCESS;
        break;
    case 'w':
        access = WRITE_ACCESS;
        break;
    case 'a':
        access = WRITE_ACCESS;
        break;
    default:
        ERROR("unreachable code, opentype=\"%s\"", opentype);
    }
    if (opentype[1] == '+') {
        access = READ_WRITE_ACCESS;
    }
    int saved_errno = 0;
    FILE* file = client_fopen(filename, "r");
    struct Inode inode;
    if (file) {
        inode = get_inode(fileno(file));
        maybe_copy_to_store(access, fileno(file), inode);
    } else {
        saved_errno = errno;
        // TODO: note the fact that the file did NOT exist
    }

    // TODO: If failed in a way that destructively-open would not fix, add op and leave

    // We opened in read mode
    // If we need any other kind of mode
    // do an open/freopen
    if (opentype[0] != 'r' || opentype[1] != '\0') {
        if (file) {
            file = client_freopen(filename, opentype, file);
        } else {
            file = client_fopen(filename, opentype);
        }
        if (file) {
            inode = get_inode(fileno(file));
        } else {
            saved_errno = errno;
        }
    }

    OpenNumber open_number = {0};
    if (file) {
        new_open_number(fileno(file));
    }
    prov_log_record((struct Op){
        .data =
            {
                .open_tag = OpData_Open,
                .open =
                    {
                        .path =
                            {
                                .directory = get_open_number(AT_FDCWD),
                                .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                            },
                        .open_number = open_number,
                        .inode = inode,
                        .flags = 0,
                        .mode = 0,
                        .dir = false,
                        .creat = false,
                    },
            },
        .ferrno = 0,
    });

    errno = saved_errno;
    return file;
}

OpenNumber close_wrapper(int fd) {
    return (OpenNumber){atomic_exchange(fd_table_address_of_strong(&fd_table, fd), 0)};
}

/*
 * Call this to indicate that the process did something (successful or not).
 */
void prov_log_record(struct Op op) {
    // TODO: construct op in op arena place instead of copying into arena.
    ASSERTF(0 <= op.data.tag && op.data.tag < OpData_Sentinel, "%d", op.data.tag);
    /* #ifdef DEBUG_LOG */
    /*     char str[PATH_MAX * 2]; */
    /*     op_to_human_readable(str, PATH_MAX * 2, &op); */
    /*     if (op.data.tag != OpData_Readdir) { */
    /*         DEBUG("recording op: %s (%d)", str, op.data.tag); */
    /*     } */
    /*     if (op.data.tag == OpData_InitExecEpoch) { */
    /*         DEBUG("Init exec:"); */
    /*         for (size_t idx = 0; op.data.init_exec_epoch.argv[idx]; ++idx) { */
    /*             fprintf(stderr, "'%s' ", op.data.init_exec_epoch.argv[idx]); */
    /*         } */
    /*         fprintf(stderr, "\n"); */
    /*     } else if (op.data.tag == OpData_Exec) { */
    /*         DEBUG("Exec:"); */
    /*         fprintf(stderr, "'%s' ", op.data.exec.path.path); */
    /*         for (size_t idx = 0; op.data.exec.argv[idx]; ++idx) { */
    /*             fprintf(stderr, "'%s' ", op.data.exec.argv[idx]); */
    /*         } */
    /*         fprintf(stderr, "\n"); */
    /*     } */
    /* #endif */

    // TODO: Time the performance of this
    //if (op.time.tv_sec == 0 && op.time.tv_nsec == 0) {
    //    EXPECT(== 0, clock_gettime(CLOCK_MONOTONIC, &op.time));
    //}
    if (op.pthread_id == 0) {
        op.pthread_id = get_pthread_id();
    }
    if (op.iso_c_thread_id == 0) {
        op.iso_c_thread_id = client_thrd_current ? client_thrd_current() : 0;
    }

    /* TODO: we currently log ops by constructing them on the stack and copying them into the arena.
     * Ideally, we would construct them in the arena (no copy necessary).
     * */
    struct Op* dest = arena_calloc(get_op_arena(), 1, sizeof(struct Op));
    probe_libc_memcpy(dest, &op, sizeof(struct Op));

    /* TODO: Special handling of ops that affect process state */

    /* Freeing up virtual memory space is good in theory,
     * but it causes errors when decoding.
     * Since freeing means that the virtual address can be reused by mmap.
     * We can only safely free the op arena.
     * If the system runs low on memory, I think Linux will page out the infrequently used mmapped regions,
     * which is what we want. */
    /* arena_uninstantiate_all_but_last(get_data_arena()); */
    /* arena_uninstantiate_all_but_last(get_op_arena()); */
}

bool prov_log_is_enabled() { return true; }
