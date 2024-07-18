static void prov_log_save() {
    /*
     * Before I was using mmap-arena, I needed to explicitly save stuff.
     * I am leaving this here, just in case.
     * */
}

static void prov_log_record(struct Op op);

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

/*
    if (op.op_code == OpenRead || op.op_code == OpenReadWrite || op.op_code == OpenOverWrite || op.op_code == OpenWritePart || op.op_code == OpenDir) {
        assert(op.dirfd);
        assert(op.path);
        assert(op.fd);
        assert(!op.inode_triple.null);
        fd_table_associate(op.fd, op.dirfd, op.path, op.inode_triple);
    } else if (op.op_code == Close) {
        fd_table_close(op.fd);
    } else if (op.op_code == Chdir) {
        if (op.path) {
            assert(op.fd == null_fd);
            fd_table_close(AT_FDCWD);
            fd_table_associate(AT_FDCWD, AT_FDCWD, op.path, op.inode_triple);
        } else {
            assert(op.fd > 0);
            fd_table_close(AT_FDCWD);
            fd_table_dup(op.fd, AT_FDCWD);
        }
    }
*/

    /* Freeing up virtual memory space is good in theory,
     * but it causes errors when decoding.
     * Since freeing means that the virtual address can be reused by mmap.
     * We can only safely free the op arena.
     * If the system runs low on memory, I think Linux will page out the infrequently used mmapped regions,
     * which is what we want. */
    /* arena_uninstantiate_all_but_last(get_data_arena()); */
    arena_uninstantiate_all_but_last(get_op_arena());
}
