static void prov_log_save() {
    /*
     * Before I was using mmap-arena, I needed to explicitly save stuff.
     * I am leaving this here, just in case.
     * */
}

static void prov_log_record(struct Op op);

bool op_is_read(struct Op op) {
    return (op.op_code == open_op_code && (op.data.open.flags & O_RDONLY || op.data.open.flags & O_RDWR))
        || op.op_code == exec_op_code
        || op.op_code == readdir_op_code
        || op.op_code == read_link_op_code;
}

bool op_is_write(struct Op op) {
    return op.op_code == open_op_code && (op.data.open.flags & O_WRONLY || op.data.open.flags & O_RDWR);
}

bool op_is_overwrite(struct Op op) {
    /* TODO: Double check flags here */
    return op.op_code == open_op_code && (op.data.open.flags & O_TRUNC || op.data.open.flags & O_CREAT);
}

int copy(const struct Path* path) {
    static char dst_path[PATH_MAX];
    path_to_id_string(path, dst_path);
    return copy_file(path->dirfd_minus_at_fdcwd + AT_FDCWD, path->path, get_inodes_dirfd(), dst_path, path->size);
}

/*
 * Call this to indicate that the process is about to do some op.
 * The values of the op that are not known before executing the call
 * (e.g., fd for open is not known before-hand)
 * just put something random in there.
 * We promise not to read those fields in this function.
 */
static void prov_log_try(struct Op op) {
    if (op.op_code == clone_op_code && op.data.clone.flags & CLONE_VFORK) {
        DEBUG("I don't know if CLONE_VFORK actually works. See libc_hooks_source.c for vfork()");
    }
    if (op.op_code == exec_op_code) {
        prov_log_record(op);
    }

    const struct Path* path = op_to_path(&op);
    if (path->path) {
        if (false) {
        } else if (op_is_read(op)) {
            inode_table_put_if_not_exists(&read_inodes, path);
        } else if (op_is_write(op)) {
            if (inode_table_contains(&read_inodes, path) && inode_table_put_if_not_exists(&copied_or_overwritten_inodes, path)) {
                DEBUG("Copying %s", path->path);
                copy(path);
            } else if (op_is_overwrite(op)) {
                inode_table_put_if_not_exists(&copied_or_overwritten_inodes, path);
            }
        }
    }
}

/*
 * Call this to indicate that the process did something (successful or not).
 */
static void prov_log_record(struct Op op) {
#ifdef DEBUG_LOG
        char str[PATH_MAX * 2];
        op_to_human_readable(str, PATH_MAX * 2, &op);
        DEBUG("record op: %s", str);
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
