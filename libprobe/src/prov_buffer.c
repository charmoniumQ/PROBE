#define _GNU_SOURCE

#include "../generated/libc_hooks.h"
#include <fcntl.h>
#include <limits.h>
#include <string.h>

#include "arena.h"
#include "debug_logging.h"
#include "global_state.h"
#include "inode_table.h"
#include "prov_utils.h"
#include "util.h"

#include "prov_buffer.h"

void prov_log_save() {
    /* TODO: ensure we call Arena save in atexit, pthread_cleanup_push */
    DEBUG("prov log save");
    arena_sync(get_op_arena());
    arena_sync(get_data_arena());
}

static inline bool is_read_op(struct Op op) {
    return (op.op_code == open_op_code &&
            (op.data.open.flags & O_RDONLY || op.data.open.flags & O_RDWR)) ||
           op.op_code == exec_op_code || op.op_code == readdir_op_code ||
           op.op_code == read_link_op_code;
}

static inline bool is_mutate_op(struct Op op) {
    return op.op_code == open_op_code &&
           (op.data.open.flags & O_WRONLY || op.data.open.flags & O_RDWR);
}

static inline bool is_replace_op(struct Op op) {
    /* TODO: Double check flags here */
    return op.op_code == open_op_code &&
           (op.data.open.flags & O_TRUNC || op.data.open.flags & O_CREAT);
}

static int copy_to_store(const struct Path* path) {
    static char dst_path[PATH_MAX];
    path_to_id_string(path, dst_path);
    /*
    ** We take precautions to avoid calling copy(f) if copy(f) is already called in the same process.
    ** But it may have been already called in a different process!
    ** Especially coreutils used in every script.
     */

    int dst_dirfd = get_inodes_dirfd();
    int access = unwrapped_faccessat(dst_dirfd, dst_path, F_OK, 0);
    if (access == 0) {
        DEBUG("Already exists %s %ld", path->path, path->inode);
        return 0;
    } else {
        DEBUG("Copying %s %ld", path->path, path->inode);
        return copy_file(path->dirfd_minus_at_fdcwd + AT_FDCWD, path->path, dst_dirfd, dst_path,
                         path->size);
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
    if (op.op_code == exec_op_code) {
        prov_log_record(op);
    }

    for (char i = 0; i < 2; ++i) {
        const struct Path* path = (i == 0) ? op_to_path(&op) : op_to_second_path(&op);
        if (should_copy_files() && path->path && path->stat_valid) {
            if (should_copy_files_lazily()) {
                if (is_read_op(op)) {
                    DEBUG("Reading %s %ld", path->path, path->inode);
                    inode_table_put_if_not_exists(get_read_inodes(), path);
                } else if (is_mutate_op(op)) {
                    if (inode_table_put_if_not_exists(get_copied_or_overwritten_inodes(), path)) {
                        DEBUG("Mutating, but not copying %s %ld since it is copied already or "
                              "overwritten",
                              path->path, path->inode);
                    } else {
                        DEBUG("Mutating, therefore copying %s %ld", path->path, path->inode);
                        if (copy_to_store(path) != 0) {
                            DEBUG("Copying failed");
                        }
                    }
                } else if (is_replace_op(op)) {
                    if (inode_table_contains(get_read_inodes(), path)) {
                        if (inode_table_put_if_not_exists(get_copied_or_overwritten_inodes(),
                                                          path)) {
                            DEBUG("Mutating, but not copying %s %ld since it is copied already or "
                                  "overwritten",
                                  path->path, path->inode);
                        } else {
                            DEBUG("Replace after read %s %ld", path->path, path->inode);
                            if (copy_to_store(path) != 0) {
                                DEBUG("Copying failed");
                            }
                        }
                    } else {
                        DEBUG("Mutating, but not copying %s %ld since it was never read",
                              path->path, path->inode);
                    }
                }
            } else if (is_read_op(op) || is_mutate_op(op)) {
                ASSERTF(should_copy_files_eagerly(), "");
                if (inode_table_put_if_not_exists(get_copied_or_overwritten_inodes(), path)) {
                    DEBUG("Not copying %s %ld because already did", path->path, path->inode);
                } else {
                    copy_to_store(path);
                }
            }
        }
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
    DEBUG("recording op: %s", str);
    if (op.op_code == exec_op_code) {
        DEBUG("Exec:");
        for (size_t idx = 0; idx < op.data.exec.envc; ++idx) {
            fprintf(stderr, "'%s'\n", op.data.exec.env[idx]);
        }
        fprintf(stderr, "'%s' ", op.data.exec.path.path);
        for (size_t idx = 0; idx < op.data.exec.argc; ++idx) {
            fprintf(stderr, "'%s' ", op.data.exec.argv[idx]);
        }
        fprintf(stderr, "\n");
    }
#endif

    if (op.time.tv_sec == 0 && op.time.tv_nsec == 0) {
        EXPECT(== 0, clock_gettime(CLOCK_MONOTONIC, &op.time));
    }
    if (op.pthread_id == 0) {
        op.pthread_id = pthread_self();
    }
    if (op.iso_c_thread_id == 0) {
        op.iso_c_thread_id = thrd_current();
    }

    /* TODO: we currently log ops by constructing them on the stack and copying them into the arena.
     * Ideally, we would construct them in the arena (no copy necessary).
     * */
    struct Op* dest = arena_calloc(get_op_arena(), 1, sizeof(struct Op));
    memcpy(dest, &op, sizeof(struct Op));

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
