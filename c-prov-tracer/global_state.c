static unsigned int __process_id = UINT_MAX;
static void init_process_id() {
    assert(__process_id == UINT_MAX);
    __process_id = getpid();
}
static pid_t get_process_id() {
    assert(__process_id != UINT_MAX);
    return __process_id;
}

static int __is_prov_root = -1;
static void init_is_prov_root() {
    assert(__is_prov_root == -1);
    const char* is_prov_root_env_var = PRIVATE_ENV_VAR_PREFIX "IS_ROOT";
    const char* is_root = getenv(is_prov_root_env_var);
    DEBUG("getenv %s = %s", is_prov_root_env_var, is_root);
    if (is_root != NULL && is_root[0] == '0') {
        __is_prov_root = 0;
    } else {
        EXPECT(== 0, setenv(is_prov_root_env_var, "0", true));
        DEBUG("setenv %s = 0", is_prov_root_env_var);
        __is_prov_root = 1;
    }
}
static bool is_prov_root() {
    assert(__is_prov_root == 1 || __is_prov_root == 0);
    return __is_prov_root;
}

/*
 * exec-family of functions _replace_ the process currently being run with a new process, by loading the specified program.
 * It has the same PID, but it is a new process.
 * Therefore, we track the "exec epoch".
 * If this PID is the same as the one in the environment, this must be a new exec epoch of the same.
 * Otherwise, it must be a truly new process.
 */
static unsigned int __exec_epoch = UINT_MAX;
static void init_exec_epoch() {
    assert(__exec_epoch == UINT_MAX);
    const char* tracee_pid_env_var = PRIVATE_ENV_VAR_PREFIX "TRACEE_PID";
    /* We will store EXEC_EPOCH_PLUS_ONE because 0 is a sentinel value for strtol. */
    const char* exec_epoch_plus_one_env_var = PRIVATE_ENV_VAR_PREFIX "EXEC_EPOCH_PLUS_ONE";
    const char* tracee_pid_str = getenv(tracee_pid_env_var);
    DEBUG("getenv %s = %s", tracee_pid_env_var, tracee_pid_str);
    const char* exec_epoch_plus_one_str = getenv(exec_epoch_plus_one_env_var);
    DEBUG("getenv %s = %s", exec_epoch_plus_one_env_var, exec_epoch_plus_one_str);
    pid_t tracee_pid = -1;
    ASSERTF(
        (exec_epoch_plus_one_str == NULL) == (tracee_pid_str == NULL),
        "I always set %s (%s) and %s (%s) at the same time, but somehow one is null and the other is not.",
        tracee_pid_env_var,
        tracee_pid_str,
        exec_epoch_plus_one_env_var,
        exec_epoch_plus_one_str
    );
    ASSERTF(
        (exec_epoch_plus_one_str == NULL) == is_prov_root(),
        "Only the prov root should experience a null %s in their environment.",
        exec_epoch_plus_one_env_var);
    if (exec_epoch_plus_one_str) {
        tracee_pid = (pid_t) EXPECT(> 0, strtol(tracee_pid_str, NULL, 10));
    }
    pid_t new_tracee_pid = get_process_id();
    __exec_epoch = 0;
    if (new_tracee_pid == tracee_pid) {
        __exec_epoch = (size_t) EXPECT(> 0, strtol(exec_epoch_plus_one_str, NULL, 10)) - 1;
    } else {
        /* the default value of new_exec_epoch is correct here. */
    }
    char new_tracee_pid_str[unsigned_int_string_size];
    char new_exec_epoch_str[unsigned_int_string_size];
    CHECK_SNPRINTF(new_tracee_pid_str, unsigned_int_string_size, "%u", new_tracee_pid);
    CHECK_SNPRINTF(new_exec_epoch_str, unsigned_int_string_size, "%u", __exec_epoch + 2);
    EXPECT(== 0, setenv(tracee_pid_env_var, new_tracee_pid_str, true));
    DEBUG("setenv %s = %s", tracee_pid_env_var, new_tracee_pid_str);
    EXPECT(== 0, setenv(exec_epoch_plus_one_env_var, new_exec_epoch_str, true));
    DEBUG("setenv %s = %s", exec_epoch_plus_one_env_var, new_exec_epoch_str);
}
static unsigned int get_exec_epoch() {
    assert(__exec_epoch != UINT_MAX);
    return __exec_epoch;
}

/*
 * Linux can technically reuse PIDs.
 * It usually doesn't happen that much, but I use the process birth_time-time as a "last-resort" in case it does.
 * */
static struct timespec __process_birth_time = {-1, 0};
static void init_process_birth_time() {
    const char* process_birth_time_env_var = PRIVATE_ENV_VAR_PREFIX "PROCESS_BIRTH_TIME";
    if (get_exec_epoch() == 0) {
        assert(__process_birth_time.tv_sec == -1 && __process_birth_time.tv_nsec == 0);
        EXPECT(== 0, clock_gettime(CLOCK_REALTIME, &__process_birth_time));
        int process_birth_time_str_length = signed_long_string_size + unsigned_long_string_size + 1;
        char process_birth_time_str[process_birth_time_str_length];
        CHECK_SNPRINTF(process_birth_time_str, process_birth_time_str_length, "%ld.%ld", __process_birth_time.tv_sec, __process_birth_time.tv_nsec);
        EXPECT(== 0, setenv(process_birth_time_env_var, process_birth_time_str, true));
        DEBUG("setenv %s = %s", process_birth_time_env_var, process_birth_time_str);
    } else {
        const char* process_birth_time_str = getenv(process_birth_time_env_var);
        DEBUG("getenv: %s = %s", process_birth_time_env_var, process_birth_time_str);
        char* rest_of_str = NULL;
        __process_birth_time.tv_sec = strtol(process_birth_time_str, &rest_of_str, 10);
        assert(rest_of_str[0] == '.');
        rest_of_str++;
        __process_birth_time.tv_nsec = strtol(rest_of_str, NULL, 10);
    }
}
static struct timespec get_process_birth_time() {
    DEBUG("process_birth_time = %ld.%ld\n", __process_birth_time.tv_sec, __process_birth_time.tv_nsec);
    return __process_birth_time;
}

/*
 * Linux can reuse a TID after one dies.
 * This is a big problem for us, so we just have our own TIDs based on an atomic thread counter.
 * */
static _Atomic unsigned int __thread_counter = 0;
static __thread unsigned int __thread_id = UINT_MAX;
static void init_sams_thread_id() {
    EXPECT(== UINT_MAX, __thread_id);
    __thread_id = __thread_counter++;
}
static unsigned int get_sams_thread_id() {
    assert(__thread_id != UINT_MAX);
    return __thread_id;
}

static int __prov_log_verbose = -1;
static void init_prov_log_verbose() {
    assert(__prov_log_verbose == -1);
    static char* const verbose_env_var = ENV_VAR_PREFIX "VERBOSE";
    char* verbose_env_val = getenv(verbose_env_var);
    if (verbose_env_val && verbose_env_val[0] != '\0') {
        __prov_log_verbose = 1;
    } else {
        __prov_log_verbose = 0;
    }
    DEBUG("getenv %s = %s", verbose_env_var, verbose_env_val);
}
static bool prov_log_verbose() {
    assert(__prov_log_verbose == 0 || __prov_log_verbose == 1);
    return __prov_log_verbose;
}

/* TODO: Hack exec-family of functions to propagate these environment variables. */

static void init_process_global_state() {
    init_prov_log_verbose();
    init_is_prov_root();
    init_process_id();
    init_exec_epoch();
    init_process_birth_time();
}

static void init_thread_global_state() {
    init_sams_thread_id();
}
