static _Atomic bool __prov_log_disable = false;

static void prov_log_disable() { __prov_log_disable = true; }
static void prov_log_enable () { __prov_log_disable = false; }
static bool prov_log_is_enabled () { return !__prov_log_disable; }
static void prov_log_set_enabled (bool value) { __prov_log_disable = value; }

OWNED const char* dirfd_path(int dirfd) {
    bool was_prov_log_enabled = prov_log_is_enabled();
    prov_log_disable();
    char proc_path[PATH_MAX];
    CHECK_SNPRINTF(proc_path, PATH_MAX, "/proc/self/fds/%d", dirfd);
    const char* ret = unwrapped_realpath(proc_path, NULL);
    prov_log_set_enabled(was_prov_log_enabled);
    return ret;
}

static __thread struct ArenaDir op_arena;
static __thread struct ArenaDir data_arena;

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
    (void) op;

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
        op_to_human_readable(str, PATH_MAX * 2, op);
        DEBUG("op: %s", str);
#endif

    if (op.time.tv_sec == 0 && op.time.tv_nsec == 0) {
        EXPECT(== 0, clock_gettime(CLOCK_MONOTONIC, &op.time));
    }

    /* TODO: we currently log ops by constructing them on the stack and copying them into the arena.
     * Ideally, we would construct them in the arena (no copy necessary).
     * */
    struct Op* dest = arena_calloc(&op_arena, 1, sizeof(struct Op));
    memcpy(dest, &op, sizeof(struct Op));

    /* TODO: Special handling of ops that affect process state */
    if (op.op_code == clone_op_code) {
        DEBUG("clone: process %d, thread %d", get_process_id(), get_sams_thread_id());
    }
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

    arena_uninstantiate_all_but_last(&op_arena);
    arena_uninstantiate_all_but_last(&data_arena);
}

static int mkdir_and_descend(int dirfd, long child, char* buffer, bool exists_ok) {
    CHECK_SNPRINTF(buffer, signed_long_string_size, "%ld", child);
    int mkdir_ret = unwrapped_mkdirat(dirfd, buffer, 0777);
    if (mkdir_ret != 0 && (!exists_ok || errno != EEXIST)) {
        ERROR("%s/%ld exists\n", dirfd_path(dirfd), child);
    }
    int sub_dirfd = EXPECT(!= -1, unwrapped_openat(dirfd, buffer, O_RDONLY | O_DIRECTORY));
    EXPECT(== 0, unwrapped_close(dirfd));
    return sub_dirfd;
}

static int __epoch_dirfd = -1;
static void init_process_prov_log() {
    /* TODO: Lock this, just in case we race somehow */
    assert(__epoch_dirfd == -1);
    static char* const dir_env_var = ENV_VAR_PREFIX "DIR";
    const char* relative_dir = debug_getenv(dir_env_var);
    if (relative_dir == NULL) {
        assert(is_prov_root());
        relative_dir = ".prov";
    }
    struct stat stat_buf;
    int stat_ret = unwrapped_fstatat(AT_FDCWD, relative_dir, &stat_buf, 0);
    if (stat_ret != 0) {
        if (0 != unwrapped_mkdirat(AT_FDCWD, relative_dir, 0755)) {
            ERROR("Could not mkdir %s", relative_dir);
        }
    } else {
        if ((stat_buf.st_mode & S_IFMT) != S_IFDIR) {
            ERROR("%s already exists but is not a directory\n", relative_dir);
        };
    }
    int cwd = EXPECT(!= -1, unwrapped_openat(AT_FDCWD, relative_dir, O_RDONLY | O_DIRECTORY));

    struct timespec process_birth_time = get_process_birth_time();
    char dir_name [signed_long_string_size + 1];
    /* Could have multiple launches per second and nanosecond even (clock granularity is rarely 1 ns even though the API is) */
    cwd = mkdir_and_descend(cwd, process_birth_time.tv_sec, dir_name, true);
    cwd = mkdir_and_descend(cwd, process_birth_time.tv_nsec, dir_name, true);
    cwd = mkdir_and_descend(cwd, get_process_id(), dir_name, true);
    __epoch_dirfd = mkdir_and_descend(cwd, get_exec_epoch(), dir_name, false);

    /* TODO: pass process_dirfd directly to subsequent exec epochs (since the default is ~O_CLOEXEC) rather than the realpath */
    char absolute_dir [PATH_MAX + 1] = {0};
    EXPECT_NONNULL(unwrapped_realpath(relative_dir, absolute_dir));
    /* Setenv, so child processes will be using the same prov log dir, even if they change directories. */
    debug_setenv(dir_env_var, absolute_dir);

    DEBUG("init_process_prov_log: %s", absolute_dir);
}

static const size_t prov_log_arena_size = 256 * 1024;
static void init_thread_prov_log() {
    pid_t thread_id = get_sams_thread_id();
    char dir_name [signed_long_string_size + 1];
    int cwd = mkdir_and_descend(__epoch_dirfd, thread_id, dir_name, false);
    EXPECT(== 0, arena_create(&op_arena, cwd, "ops", prov_log_arena_size));
    EXPECT(== 0, arena_create(&data_arena, cwd, "data", prov_log_arena_size));

    DEBUG("init_thread_prov_log: %d", thread_id);
}

static void prov_log_term_process() { }

static struct Path create_path_lazy(int dirfd, BORROWED const char* path) {
    if (likely(prov_log_is_enabled())) {
        struct Path ret = {
            dirfd - AT_FDCWD,
            (path != NULL ? EXPECT_NONNULL(arena_strndup(&data_arena, path, PATH_MAX)) : NULL),
            -1,
            -1,
            -1,
            false,
            true,
        };

        /*
         * If dirfd == 0, then the user is asserting it is not needed.
         * Path must be absolute. */
        assert(dirfd != 0 || (path != NULL && path[0] == '/'));

        /*
         * if path == NULL, then the target is the dir specified by dirfd.
         * */
        struct stat stat_buf;
        int stat_ret;
        /* TODO: convert to statx */
        prov_log_disable();
        if (path == NULL) {
            stat_ret = unwrapped_fstat(dirfd, &stat_buf);
        } else {
            stat_ret = unwrapped_fstatat(dirfd, path, &stat_buf, 0);
        }
        prov_log_enable();
        if (stat_ret == 0) {
            ret.device_major = major(stat_buf.st_dev);
            ret.device_minor = minor(stat_buf.st_dev);
            ret.inode = stat_buf.st_ino;
            ret.stat_valid = true;
        }
        return ret;
    } else {
        return null_path;
    }
}

struct InitExecEpochOp init_current_exec_epoch() {
    extern char *__progname;
    struct InitExecEpochOp ret = {
        .process_id = get_process_id(),
        .process_birth_time = get_process_birth_time(),
        .exec_epoch = get_exec_epoch(),
        .program_name = arena_strndup(&data_arena, __progname, PATH_MAX),
    };
    return ret;
}
