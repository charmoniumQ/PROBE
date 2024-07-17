/*
 * For each member of global state $X of type $T, we have
 *
 *     const $T __$X_initial = invalid_value_sentinel;
 *     $T __$X = __$X_initial;
 *     static void init_$X();
 *     static $T get_$X();
 *     static $T get_$X_safe();
 *
 * __$X_initial should be an invalid value (or at least very rare value) of $X.
 *
 * Most client code should assume $X has already been initialized, and call get_$X().
 *
 * However, in some instances (so far only used in debug logging), we may need to access before they would have been bootstrapped.
 * In such case, client code should call get_$X_safe(), which will test if $X is initialized, and if not, return a sentinel value
 *
 */

static const int __is_proc_root_initial = -1;
static int __is_proc_root = __is_proc_root_initial;
static const char* is_proc_root_env_var = PRIVATE_ENV_VAR_PREFIX "IS_ROOT";
static void init_is_proc_root() {
    assert(__is_proc_root == __is_proc_root_initial);
    const char* is_root = debug_getenv(is_proc_root_env_var);
    if (is_root != NULL) {
        assert(is_root[0] == '0' && is_root[1] == '\0');
        __is_proc_root = 0;
    } else {
        __is_proc_root = 1;
    }
    DEBUG("Is proc root? %d", __is_proc_root);
}
static bool is_proc_root() {
    assert(__is_proc_root == 1 || __is_proc_root == 0);
    return __is_proc_root;
}

/*
 * exec-family of functions _rep\lace_ the process currently being run with a new process, by loading the specified program.
 * It has the same PID, but it is a new process.
 * Therefore, we track the "exec epoch".
 * If this PID is the same as the one in the environment, this must be a new exec epoch of the same.
 * Otherwise, it must be a truly new process.
 */
static const int __exec_epoch_initial = -1;
static int __exec_epoch = __exec_epoch_initial;
static const char* exec_epoch_env_var = PRIVATE_ENV_VAR_PREFIX "EXEC_EPOCH";
static const char* pid_env_var = PRIVATE_ENV_VAR_PREFIX "PID";
static void init_exec_epoch() {
    assert(__exec_epoch == __exec_epoch_initial);

    if (!is_proc_root()) {
        const char* last_epoch_pid_str = debug_getenv(pid_env_var);
        if (!last_epoch_pid_str) {
            ERROR("Internal environment variable \"%s\" not set", pid_env_var);
        }

        pid_t last_epoch_pid = EXPECT(> 0, my_strtoul(last_epoch_pid_str, NULL, 10));

        if (last_epoch_pid == getpid()) {
            const char* exec_epoch_str = debug_getenv(exec_epoch_env_var);
            if (!last_epoch_pid_str) {
                ERROR("Internal environment variable \"%s\" not set", exec_epoch_env_var);
            }

            size_t last_exec_epoch = EXPECT(>= 0, my_strtoul(exec_epoch_str, NULL, 10));
            /* Since zero is a sentinel value for strtol,
             * if it returns zero,
             * there's a small chance that exec_epoch_str is an invalid int,
             * We cerify manually */
            assert(last_exec_epoch != 0 || exec_epoch_str[0] == '0');

            __exec_epoch = last_exec_epoch + 1;
        } else {
            __exec_epoch = 0;
        }
    } else {
        __exec_epoch = 0;
    }

    DEBUG("exec_epoch = %d", __exec_epoch);
}
static int get_exec_epoch() {
    assert(__exec_epoch != __exec_epoch_initial);
    return __exec_epoch;
}
static int get_exec_epoch_safe() {
    return __exec_epoch;
}

static int mkdir_and_descend(int dirfd, long child, bool mkdir, bool close) {
    char buffer[signed_long_string_size + 1];
    CHECK_SNPRINTF(buffer, signed_long_string_size, "%ld", child);
    if (mkdir) {
        int mkdir_ret = unwrapped_mkdirat(dirfd, buffer, 0777);
        if (mkdir_ret != 0) {
            int saved_errno = errno;
#ifndef NDEBUG
            listdir(dirfd_path(dirfd), 2);
#endif
            ERROR("Cannot mkdir %s/%ld: %s", dirfd_path(dirfd), child, strerror(saved_errno));
        }
    }
    int sub_dirfd = unwrapped_openat(dirfd, buffer, O_RDONLY | O_DIRECTORY);
    if (sub_dirfd == -1) {
        int saved_errno = errno;
#ifndef NDEBUG
        listdir(dirfd_path(dirfd), 2);
#endif
        DEBUG("dirfd=%d buffer=\"%s\"", dirfd, buffer);
        ERROR("Cannot openat %s/%ld (did we do mkdir? %d): %s", dirfd_path(dirfd), child, mkdir, strerror(saved_errno));
    }
    if (close) {
        EXPECT(== 0, unwrapped_close(dirfd));
    }
    return sub_dirfd;
}

static const int initial_epoch_dirfd = -1;
static int __epoch_dirfd = initial_epoch_dirfd;
static const char* probe_dir_env_var = PRIVATE_ENV_VAR_PREFIX "DIR";
static char __probe_dir[PATH_MAX + 1];
static void init_probe_dir() {
    assert(__epoch_dirfd == initial_epoch_dirfd);
    if (__probe_dir[0] == '\0') {
        // Get initial probe dir
        const char* probe_dir_env_val = debug_getenv(probe_dir_env_var);
        if (!probe_dir_env_val) {
            ERROR("Internal environment variable \"%s\" not set", probe_dir_env_var);
        }
        strncpy(__probe_dir, probe_dir_env_val, PATH_MAX);
        if (__probe_dir[0] != '/') {
            ERROR("PROBE dir \"%s\" is not absolute", __probe_dir);
        }
        if (!is_dir(__probe_dir)) {
            ERROR("PROBE dir \"%s\" is not a directory", __probe_dir);
        }
    }
    int probe_dirfd = unwrapped_openat(AT_FDCWD, __probe_dir, O_RDONLY | O_DIRECTORY);
    if (probe_dirfd < 0) {
        ERROR("Could not open \"%s\"", __probe_dir);
    }

    DEBUG("probe_dir = \"%s\"", __probe_dir);

    int pid_dirfd = mkdir_and_descend(probe_dirfd, getpid(), get_exec_epoch() == 0, true);
    __epoch_dirfd = mkdir_and_descend(pid_dirfd, get_exec_epoch(), my_gettid() == getpid(), true);
    DEBUG("__epoch_dirfd=%d (%s/%d/%d)", __epoch_dirfd, __probe_dir, getpid(), get_exec_epoch());
}
static int get_epoch_dirfd() {
    assert(__epoch_dirfd != initial_epoch_dirfd);
    assert(fd_is_valid(__epoch_dirfd));
    return __epoch_dirfd;
}

static __thread struct ArenaDir __op_arena = { 0 };
static __thread struct ArenaDir __data_arena = { 0 };
static const size_t prov_log_arena_size = 64 * 1024;
static void init_log_arena() {
    assert(!arena_is_initialized(&__op_arena));
    assert(!arena_is_initialized(&__data_arena));
    DEBUG("Going to \"%s/%d/%d/%d\" (mkdir %d)", __probe_dir, getpid(), get_exec_epoch(), my_gettid(), true);
    int thread_dirfd = mkdir_and_descend(get_epoch_dirfd(), my_gettid(), true, false);
    EXPECT( == 0, arena_create(&__op_arena, thread_dirfd, "ops", prov_log_arena_size));
    EXPECT( == 0, arena_create(&__data_arena, thread_dirfd, "data", prov_log_arena_size));
}
static struct ArenaDir* get_op_arena() {
    assert(arena_is_initialized(&__op_arena));
    return &__op_arena;
}
static struct ArenaDir* get_data_arena() {
    assert(arena_is_initialized(&__data_arena));
    return &__data_arena;
}

/**
 * Aggregate functions;
 * These functions call the init_* functions above */

static void init_process_global_state() {
    init_is_proc_root();
    init_exec_epoch();
    init_probe_dir();
}

static void init_thread_global_state() {
    init_log_arena();
}

/*
 * After a fork, the process will _appear_ to be initialized, but not be truly initialized.
 * E.g., __exec_epoch will be wrong.
 * Therefore, we will reset all the things and call init again.
 */
static void reinit_process_global_state() {
    __is_proc_root = 0;
    __exec_epoch = 0;
    __epoch_dirfd = initial_epoch_dirfd;
    init_probe_dir();
}

static void reinit_thread_global_state() {
    /*
     * We don't know if CLONE_FILES was set.
     * We will conservatively assume it is (NOT safe to call arena_destroy)
     * But we assume we have a new memory space, we should clear the mem-mappings.
     * */
    arena_drop_after_fork(&__op_arena);
    arena_drop_after_fork(&__data_arena);
    init_log_arena();
}

static char* const* update_env_with_probe_vars(char* const* user_env) {
    /* Define env vars we care about */
    const char* probe_vars[] = {
        is_proc_root_env_var,
        exec_epoch_env_var,
        pid_env_var,
        probe_dir_env_var,
        /* TODO: include LD_PRELOAD */
    };
    char exec_epoch_str[unsigned_int_string_size];
    CHECK_SNPRINTF(exec_epoch_str, unsigned_int_string_size, "%d", get_exec_epoch());
    char pid_str[unsigned_int_string_size];
    CHECK_SNPRINTF(pid_str, unsigned_int_string_size, "%d", getpid());
    const char* probe_vals[] = {
        "0",
        exec_epoch_str,
        pid_str,
        __probe_dir,
    };
    const size_t probe_var_count = sizeof(probe_vars) / sizeof(char*);

    /* Precompute some shiz */
    size_t probe_var_lengths[10] = { 0 };
    for (size_t i = 0; i < probe_var_count; ++i) {
        probe_var_lengths[i] = strlen(probe_vars[i]);
    }
    char* probe_entries[10] = { NULL };
    for (size_t i = 0; i < probe_var_count; ++i) {
        size_t probe_val_length = strlen(probe_vals[i]);
        probe_entries[i] = malloc(probe_var_lengths[i] + 1 + probe_val_length + 1);
        memcpy(probe_entries[i], probe_vars[i], probe_var_lengths[i]);
        probe_entries[i][probe_var_lengths[i]] = '=';
        memcpy(probe_entries[i] + probe_var_lengths[i] + 1, probe_vals[i], probe_val_length);
        probe_entries[i][probe_var_lengths[i] + 1 + probe_val_length] = '\0';
        DEBUG("Exporting %s", probe_entries[i]);
    }

    /* Compute user's size */
    size_t user_env_size = 0;
    for (char* const* arg = user_env; *arg; ++arg) {
        ++user_env_size;
    }

    /* Allocate a new env, based on the user's requested env, with our probe vars */
    char** new_env = malloc((user_env_size + probe_var_count + 1) * sizeof(char*));
    if (!new_env) {
        ERROR("Out of mem");
    }

    /* Copy user's env to new env
     * Clear out existence of probe_vars, if they happen to exist in the user's requested env.
     * */
    size_t new_env_size = 0;
    for (char* const* ep = user_env; *ep; ++ep) {
        bool is_probe_var = false;
        for (size_t i = 0; i < probe_var_count; ++i) {
            if (memcmp(*ep, probe_vars[i], probe_var_lengths[i]) == 0 && (*ep)[probe_var_lengths[i]] == '=') {
                is_probe_var = true;
                break;
            }
        }
        if (!is_probe_var) {
            new_env[new_env_size] = *ep;
            new_env_size++;
        }
    }

    /*
     * Now add our _desired_ versions of the probe vars we care about.
     */
    for (size_t i = 0; i < probe_var_count; ++i) {
        new_env[new_env_size + i] = probe_entries[i];
    }

    /* Top it off with a NULL */
    new_env[new_env_size + probe_var_count] = NULL;

    return new_env;
}

static void putenv_probe_vars() {
    /* TODO: We shouldn't doo this.
     * Because it makes observable changes to the parent process.
     * Instead, we should turn execv into execve and use update_env_with_probe_vars(copy(environ)). */

    /* Define env vars we care about */
    const char* probe_vars[] = {
        is_proc_root_env_var,
        exec_epoch_env_var,
        pid_env_var,
        probe_dir_env_var,
    };
    char exec_epoch_str[unsigned_int_string_size];
    CHECK_SNPRINTF(exec_epoch_str, unsigned_int_string_size, "%d", get_exec_epoch());
    char pid_str[unsigned_int_string_size];
    CHECK_SNPRINTF(pid_str, unsigned_int_string_size, "%d", getpid());
    const char* probe_vals[] = {
        "0",
        exec_epoch_str,
        pid_str,
        __probe_dir,
    };
    const size_t probe_var_count = sizeof(probe_vars) / sizeof(char*);

    for (size_t i = 0; i < probe_var_count; ++i) {
        setenv(probe_vars[i], probe_vals[i], 1 /* overwrite*/);
    }
}
