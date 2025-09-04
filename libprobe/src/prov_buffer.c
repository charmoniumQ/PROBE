#define _GNU_SOURCE

#include "prov_buffer.h"

#include <fcntl.h>    // for AT_FDCWD, O_RDWR, O_CREAT
#include <limits.h>   // IWYU pragma: keep for PATH_MAX
#include <sched.h>    // for CLONE_VFORK
#include <stdbool.h>  // for bool, true
#include <stdio.h>    // for fprintf, stderr
#include <sys/stat.h> // for S_IFMT, S_IFCHR, S_IFDIR
#include <threads.h>  // for thrd_current
#include <time.h>     // IWYU pragma: keep for timespec, clock_gettime
#include <unistd.h>   // for F_OK
// IWYU pragma: no_include "bits/time.h"    for CLOCK_MONOTONIC
// IWYU pragma: no_include "linux/limits.h" for PATH_MAX

#include "../generated/bindings.h"        // for CopyFiles
#include "../include/libprobe/prov_ops.h" // for Op, Path, OpCode, Op::(ano...
#include "arena.h"                        // for arena_sync, arena_calloc
#include "debug_logging.h"                // for DEBUG, ASSERTF, DEBUG_LOG
#include "global_state.h"                 // for get_copied_or_overwritten_...
#include "inode_table.h"                  // for inode_table_put_if_not_exists
#include "probe_libc.h"                   // for probe_libc_memcpy, probe_copy_file
#include "prov_utils.h"                   // for op_to_human_readable, op_t...

void prov_log_save() {
    /* TODO: ensure we call Arena save in atexit, pthread_cleanup_push */
    DEBUG("prov log save");
    arena_sync(get_op_arena());
    arena_sync(get_data_arena());
}

enum Access {
    READ_ACCESS,
    TRUNCATE_WRITE_ACCESS,
    WRITE_ACCESS,
    READ_WRITE_ACCESS,
    UNKNOWN_ACCESS,
};

static int copy_to_store(const struct Path* path) {
    static thread_local struct FixedPath store_path;
    static thread_local bool initialized = false;
    if (!initialized) {
        store_path = *get_probe_dir();
        initialized = true;
    }
    store_path.bytes[store_path.len] = '/';
    path_to_id_string(path, store_path.bytes + store_path.len + 1);
    /*
    ** We take precautions to avoid calling copy(f) if copy(f) is already called in the same process.
    ** But it may have been already called in a different process!
    ** Especially coreutils used in every script.
     */
    result access = probe_libc_faccessat(AT_FDCWD, store_path.bytes, F_OK);
    if (access == 0) {
        DEBUG("Already exists %s %ld", path->path, path->inode);
        return 0;
    } else if ((path->mode & S_IFMT) == S_IFDIR) {
        DEBUG("Copying directory %s %ld", path->path, path->inode);
        // TODO: implement this
        // We need to copy the inode metadata (not actual contents) linked in this directory
        return 0;
    } else if ((path->mode & S_IFMT) == S_IFREG) {
        DEBUG("Copying regular file %s %ld", path->path, path->inode);
        return copy_file(path->dirfd_minus_at_fdcwd + AT_FDCWD, path->path, AT_FDCWD,
                         store_path.bytes, path->size);
    } else if ((path->mode & S_IFMT) == S_IFCHR) {
        DEBUG("Copying block device file %s %ld", path->path, path->inode);
        // TODO
        return 0;
    } else {
        ERROR("Not sure how to copy special file %s %ld %d", path->path, path->inode,
              path->mode & S_IFMT);
        return 0;
    }
}

static void maybe_copy_to_store(enum Access access, struct Path* path) {
    enum CopyFiles mode = get_copy_files_mode();
    if ((mode == CopyFiles_Lazily || mode == CopyFiles_Eagerly) && path->path && path->stat_valid) {
        if (mode == CopyFiles_Lazily) {
            if (access == READ_ACCESS) {
                DEBUG("Reading %s %ld", path->path, path->inode);
                inode_table_put_if_not_exists(get_read_inodes(), path);
            } else if (access == READ_WRITE_ACCESS || access == WRITE_ACCESS) {
                if (inode_table_put_if_not_exists(get_copied_or_overwritten_inodes(), path)) {
                    DEBUG("Mutating, but not copying %s %ld since it is copied already or "
                          "overwritten",
                          path->path, path->inode);
                } else {
                    DEBUG("Mutating, therefore copying %s %ld", path->path, path->inode);
                    if (copy_to_store(path) != 0) {
                        WARNING("Copying failed");
                    }
                }
            } else if (access == TRUNCATE_WRITE_ACCESS) {
                if (inode_table_contains(get_read_inodes(), path)) {
                    if (inode_table_put_if_not_exists(get_copied_or_overwritten_inodes(), path)) {
                        DEBUG("Mutating, but not copying %s %ld since it is copied already or "
                              "overwritten",
                              path->path, path->inode);
                    } else {
                        DEBUG("Replace after read %s %ld", path->path, path->inode);
                        if (copy_to_store(path) != 0) {
                            WARNING("Copying failed");
                        }
                    }
                } else {
                    DEBUG("Mutating, but not copying %s %ld since it was never read", path->path,
                          path->inode);
                }
            }
        } else if (access == READ_ACCESS || access == READ_WRITE_ACCESS || access == WRITE_ACCESS) {
            ASSERTF(mode == CopyFiles_Eagerly, "");
            if (inode_table_put_if_not_exists(get_copied_or_overwritten_inodes(), path)) {
                DEBUG("Not copying %s %ld because already did", path->path, path->inode);
            } else {
                if (copy_to_store(path) != 0) {
                    WARNING("Copying failed");
                }
            }
        }
    }
}

/*
 * Call this to indicate that the process is about to do some op.
 * The values of the op that are not known before executing the call
 * (e.g., fd for open is not known before-hand)
 * just put something random in there.
 * We promise not to read those fields in this function.
 */
void prov_log_try(struct Op op) {
    ASSERTF(FIRST_OP_CODE < op.op_code && op.op_code < LAST_OP_CODE, "%d", op.op_code);

    if (op.op_code == clone_op_code && op.data.clone.flags & CLONE_VFORK) {
        DEBUG("I don't know if CLONE_VFORK actually works. See libc_hooks_source.c for vfork()");
    }

    /* Think about copying files if necessary */
    switch (op.op_code) {
    case open_op_code: {
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
            ASSERTF(false, "unreachable code, %s %d", op.data.open.path.path,
                    op.data.open.flags & O_ACCMODE);
        }
        maybe_copy_to_store(access, &op.data.open.path);
        break;
    }
    case exec_op_code: {
        maybe_copy_to_store(READ_ACCESS, &op.data.exec.path);
        break;
    }
    case spawn_op_code: {
        maybe_copy_to_store(READ_ACCESS, &op.data.spawn.exec.path);
        break;
    }
    default:
        break;
    }
}

/*
 * Call this to indicate that the process did something (successful or not).
 */
void prov_log_record(struct Op op) {
    // TODO: construct op in op arena place instead of copying into arena.
    ASSERTF(FIRST_OP_CODE < op.op_code && op.op_code < LAST_OP_CODE, "%d", op.op_code);
#ifdef DEBUG_LOG
    char str[PATH_MAX * 2];
    op_to_human_readable(str, PATH_MAX * 2, &op);
    if (op.op_code != readdir_op_code) {
        DEBUG("recording op: %s", str);
    }
    if (op.op_code == init_exec_epoch_op_code) {
        DEBUG("Init exec:");
        for (size_t idx = 0; op.data.init_exec_epoch.argv[idx]; ++idx) {
            fprintf(stderr, "'%s' ", op.data.init_exec_epoch.argv[idx]);
        }
        fprintf(stderr, "\n");
    } else if (op.op_code == exec_op_code) {
        DEBUG("Exec:");
        fprintf(stderr, "'%s' ", op.data.exec.path.path);
        for (size_t idx = 0; op.data.exec.argv[idx]; ++idx) {
            fprintf(stderr, "'%s' ", op.data.exec.argv[idx]);
        }
        fprintf(stderr, "\n");
    }
#endif

    // TODO: Time the performance of this
    //if (op.time.tv_sec == 0 && op.time.tv_nsec == 0) {
    //    EXPECT(== 0, clock_gettime(CLOCK_MONOTONIC, &op.time));
    //}
    if (op.pthread_id == 0) {
        op.pthread_id = get_pthread_id();
    }
    if (op.iso_c_thread_id == 0) {
        op.iso_c_thread_id = thrd_current();
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
    arena_uninstantiate_all_but_last(get_op_arena());
}

bool prov_log_is_enabled() { return true; }
