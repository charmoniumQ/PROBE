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
// IWYU pragma: no_include "bits/posix1_lim.h" for SSIZE_MAX, we have limits.h
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
#include "libc_subset.h"              // for fileno
#include "linux/stat.h"               // for statx, STATX_CTIME, STATX_INO
#include "probe_libc.h"               // for probe_copy_file, probe_libc_fa...
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
        string, PATH_MAX, "/inodes/%04x-%04x-%016lx-%016lldx-%08x-%016lx", inode.device_major,
        inode.device_minor, inode.number,
        /* In GCC, this field is long int; in Clang, it is long long int. Always cast to the larger */
        (long long int)inode.mtime.tv_sec, inode.mtime.tv_nsec, inode.size);
}

int copy_file(int src_fd, int dst_dirfd, const char* _Nullable dst_path, ssize_t size) {
    // See https://stackoverflow.com/a/2180157
    int dst_fd = client_openat(dst_dirfd, dst_path, O_WRONLY | O_CREAT, 0666);
    if (dst_fd < 0) {
        DEBUG("Error at openat");
        return (result)-dst_fd;
    }

    bool error = false;
    off_t copied = 0;
    while (copied < size) {
        ssize_t written = client_sendfile(dst_fd, src_fd, &copied, SSIZE_MAX);
        if (written < 0) {
            DEBUG("sendfile error %ld copied=%ld of %ld", -written, copied, size);
            error = true;
            break;
        }
        copied += written;
    }

    if (error) {
        // Error on first sendfile
        // File might not support sendfile.
        // Keep in mind that size can be wrong
        // In these cases, we want to fall back to normal read/writes
#define BLOCK_SIZE 4096
        while (copied < size) {
            static char buffer[BLOCK_SIZE];
            size_t remaining = size - copied;
            ssize_t read = client_pread(src_fd, buffer,
                                        remaining < BLOCK_SIZE ? remaining : BLOCK_SIZE, copied);
            if (read < 0) {
                DEBUG("Error at read");
                client_close(dst_fd);
                return read;
            }
            if (read == 0) {
                break;
            }
            off_t new_position = copied + read;
            while (copied < new_position) {
                ssize_t written = client_pwrite(dst_fd, buffer, new_position - copied, copied);
                if (written <= 0) {
                    DEBUG("Error at write");
                    client_close(dst_fd);
                    return (int)-written;
                }
                copied += written;
            }
        }
    }

    client_close(dst_fd);

    return 0;
}

static int copy_to_store(int fd, struct Inode inode) {
    static thread_local struct FixedPath store_path;
    static thread_local bool initialized = false;
    if (!initialized) {
        store_path = *get_probe_dir();
        initialized = true;
    }
    path_to_id_string(inode, store_path.bytes + store_path.len);
    /*
    ** We take precautions to avoid calling copy(f) if copy(f) is already called in the same process.
    ** But it may have been already called in a different process!
    ** Especially coreutils used in every script.
     */
    result access = probe_libc_faccessat(AT_FDCWD, store_path.bytes, F_OK);
    if (access == 0) {
        return 0;
    } else if ((inode.mode & S_IFMT) == S_IFDIR) {
        DEBUG("Can't copy directory %ld", inode.number);
        // TODO: implement this
        return 0;
    } else if ((inode.mode & S_IFMT) == S_IFREG) {
        DEBUG("Copying regular file fd=%d, dev=%d,%d, inode=%ld to path=%s", fd, inode.device_major,
              inode.device_minor, inode.number, store_path.bytes);
        return (int)copy_file(fd, AT_FDCWD, store_path.bytes, inode.size);
    } else if ((inode.mode & S_IFMT) == S_IFCHR) {
        DEBUG("Ignoring block device file %ld", inode.number);
        return 0;
    } else {
        ERROR("Not sure how to copy special file inode=%ld, (mode & S_IFMT)=%d", inode.number,
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
        ASSERTF(inode.number <= (1L << 32),
                "Unexpectedly large inode, %lu. Resize inode table levels", inode.number);
        uint64_t index = (((uint64_t)(inode.device_major)) << 48L) |
                         (((uint64_t)(inode.device_minor)) << 32L) | inode.number;
        if (mode == CopyFiles_Lazily) {
            if (access == READ_ACCESS) {
                DEBUG("Reading %ld", inode.number);
                _Atomic(bool)* _Nonnull read_loc =
                    inode_table_address_of_strong(&read_inodes, index);
                atomic_store(read_loc, true);
            } else if (access == READ_WRITE_ACCESS || access == WRITE_ACCESS) {
                _Atomic(bool)* _Nonnull coo_loc =
                    inode_table_address_of_strong(&copied_or_overwritten_inodes, index);
                if (atomic_exchange(coo_loc, true)) {
                    DEBUG("Mutating, but not copying %ld since it is copied already or "
                          "overwritten",
                          inode.number);
                } else {
                    DEBUG("Mutating, therefore copying %ld", inode.number);
                    int ret = copy_to_store(fd, inode);
                    if (ret != 0) {
                        ERROR("Copying failed, %d", ret);
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
                              inode.number);
                    } else {
                        DEBUG("Replace after read %ld", inode.number);
                        int ret = copy_to_store(fd, inode);
                        if (ret != 0) {
                            ERROR("Copying failed, %d", ret);
                        }
                    }
                } else {
                    DEBUG("Mutating, but not copying %ld since it was never read", inode.number);
                }
            }
        } else if (access == READ_ACCESS || access == READ_WRITE_ACCESS || access == WRITE_ACCESS) {
            ASSERTF(mode == CopyFiles_Eagerly, "");
            _Atomic(bool)* _Nonnull coo_loc =
                inode_table_address_of_strong(&copied_or_overwritten_inodes, index);
            if (atomic_exchange(coo_loc, true)) {
                DEBUG("Not copying %ld because already did", inode.number);
            } else {
                int ret = copy_to_store(fd, inode);
                if (ret != 0) {
                    ERROR("Copying failed, %d", ret);
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
    if (statx_buf.stx_ino == 0) {
        ERROR("Weird inode for %d: dev=%u_%u ino=%llu %d %lld %lld %llu", fd,
              statx_buf.stx_dev_major, statx_buf.stx_dev_minor, statx_buf.stx_ino,
              statx_buf.stx_mode, statx_buf.stx_mtime.tv_sec, statx_buf.stx_ctime.tv_sec,
              statx_buf.stx_size);
    }
    return (struct Inode){
        .device_major = statx_buf.stx_dev_major,
        .device_minor = statx_buf.stx_dev_minor,
        .number = statx_buf.stx_ino,
        .mode = statx_buf.stx_mode,
        .mtime = *(struct StatxTimestamp*)&statx_buf.stx_mtime,
        .ctime = *(struct StatxTimestamp*)&statx_buf.stx_ctime,
        .size = statx_buf.stx_size,
    };
}

static struct FdTable fd_table;

const uint16_t MIN_OPEN_NUMBER = 3;
const uint16_t NUMBER_MASK = 0x3FFF;
const uint16_t WRITE_BIT = 0x8000;
const uint16_t READ_BIT = 0x4000;

OpenNumber get_open_number(int fd) {
    uint16_t number = atomic_load(fd_table_address_of_strong(&fd_table, fd));
    return (OpenNumber){.fd = fd, .number = number};
}

/* Return the old open number and mark it as invalid in the future. */
OpenNumber reset_open_number(int fd) {
    uint16_t number = atomic_load(fd_table_address_of_strong(&fd_table, fd));
    DEBUG("reset_open_number: %d,%u", fd, number & NUMBER_MASK);
    return (OpenNumber){.fd = fd, .number = number};
}

OpenNumber new_open_number(int fd) {
    _Atomic(uint16_t)* address = fd_table_address_of_strong(&fd_table, fd);
    uint16_t old_number = atomic_load(address) & 0x3FFF;
    uint16_t new_number;
    if (old_number == 0) {
        new_number = MIN_OPEN_NUMBER;
    } else {
        new_number = old_number + 1;
    }
    atomic_store(address, new_number);
    ASSERTF(new_number >= MIN_OPEN_NUMBER, "");
    DEBUG("new_open_number: %d,%u", fd, new_number);
    return (OpenNumber){
        .fd = fd,
        .number = new_number,
    };
}

void mark_access(int fd, bool is_write) {
    _Atomic(uint16_t)* address = fd_table_address_of_strong(&fd_table, fd);
#ifndef NDEBUG
    uint16_t number = atomic_load(address) & NUMBER_MASK;
    DEBUG("Mark %d,%d as %s", fd, number, is_write ? "write" : "read");
#endif
    atomic_fetch_or(address, is_write ? WRITE_BIT : READ_BIT);
}

int open_wrapper(int dirfd, const char* filename, int flags, mode_t mode) {
    int saved_errno = errno;
    errno = 0;
    int call_errno = 0;
    enum AccessType access;
    if ((flags & O_ACCMODE) == O_RDONLY) {
        access = READ_ACCESS;
    } else if (flags & O_TRUNC) {
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
    int fd = client_openat(dirfd, filename, nondestructive_flags, mode);
    call_errno = errno;
    struct Inode inode;
    if (fd >= 0) {
        inode = get_inode(fd);
        maybe_copy_to_store(access, fd, inode);
    }

    // TODO: If failed in a way that destructively-open would not fix, add op and leave

    if (flags != nondestructive_flags) {
        if (fd >= 0) {
            client_close(fd);
        }
        // TODO: try interpreting flags instead of doing close+open
        fd = client_openat(dirfd, filename, flags, mode);
        call_errno = errno;
        if (fd >= 0) {
            inode = get_inode(fd);
        }
    }

    if (fd >= 0) {
        OpenNumber open_number = new_open_number(fd);
        DEBUG("on %d,%d; inode %lu; dev=%d,%d", open_number.fd, open_number.number, inode.number,
              inode.device_major, inode.device_minor);
        ASSERTF(open_number.number > 0, "");
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
                            /* This is only used when we _know_ that the file was created, like in pipe() */
                            .creat = false,
                        },
                },
            .ferrno = 0,
        });
    }
    if (call_errno == 0) {
        errno = saved_errno;
    } else {
        errno = call_errno;
    }
    return fd;
}

const int ACCESS_FLAGS[] = {
    [READ_ACCESS] = O_RDONLY,
    [WRITE_ACCESS] = O_WRONLY,
    [READ_WRITE_ACCESS] = O_RDWR,
    [TRUNCATE_WRITE_ACCESS] = O_WRONLY | O_TRUNC,
};

FILE* fopen_wrapper(const char* filename, const char* opentype) {
    int saved_errno = errno;
    errno = 0;
    int call_errno;
    DEBUG("fopen_wrapper(\"%s\", \"%s\")", filename, opentype);
    bool has_plus = false;
    for (const char* f = filename; *f; ++f) {
        if (*f == '+') {
            has_plus = true;
            break;
        }
    }
    enum AccessType access;
    if (opentype[0] == 'w') {
        // "w" or "w+"
        access = TRUNCATE_WRITE_ACCESS;
    } else if (has_plus) {
        access = READ_WRITE_ACCESS;
    } else if (opentype[0] == 'a') {
        access = WRITE_ACCESS;
    } else if (opentype[0] == 'r') {
        access = READ_ACCESS;
    } else {
        ERROR("unrecognized opentype: \"%s\"", opentype);
    }
    FILE* file = client_fopen(filename, "r");
    call_errno = errno;
    struct Inode inode;
    if (file) {
        inode = get_inode(fileno(file));
        maybe_copy_to_store(access, fileno(file), inode);
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
        call_errno = errno;
        if (file) {
            inode = get_inode(fileno(file));
        }
    }

    if (file) {
        OpenNumber open_number = new_open_number(fileno(file));
        DEBUG("on %d,%d; ret=FILE %p, inode %lu; dev=%d,%d", open_number.fd, open_number.number,
              file, inode.number, inode.device_major, inode.device_minor);
        ASSERTF(open_number.number > 0, "");
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
                            .flags = ACCESS_FLAGS[access],
                            .mode = 0,
                            .dir = false,
                            .creat = false,
                        },
                },
            .ferrno = 0,
        });
    }
    if (call_errno == 0) {
        errno = saved_errno;
    } else {
        errno = call_errno;
    }
    return file;
}

/*
 * Call this to indicate that the process did something (successful or not).
 */
void prov_log_record(struct Op op) {
    // TODO: construct op in op arena place instead of copying into arena.
    ASSERTF(0 <= op.data.tag && op.data.tag < OpData_Sentinel, "%d", op.data.tag);

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
