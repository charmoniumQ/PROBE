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

static const unsigned int __process_id_initial = UINT_MAX;
static unsigned int __process_id = __process_id_initial;
static void init_process_id() {
    assert(__process_id == __process_id_initial);
    __process_id = getpid();
    DEBUG("process_id = %d", __process_id);
}
static unsigned int get_process_id() {
    assert(__process_id != __process_id_initial);
    return __process_id;
}
static unsigned int get_process_id_safe() {
    return __process_id;
}

static const int __is_prov_root_initial = -1;
static int __is_prov_root = __is_prov_root_initial;
static void init_is_prov_root() {
    assert(__is_prov_root == __is_prov_root_initial);
    const char* is_prov_root_env_var = PRIVATE_ENV_VAR_PREFIX "IS_ROOT";
    const char* is_root = debug_getenv(is_prov_root_env_var);
    if (is_root != NULL && is_root[0] == '0') {
        __is_prov_root = 0;
    } else {
        debug_setenv(is_prov_root_env_var, "0", true);
        __is_prov_root = 1;
    }
}
#ifndef NDEBUG
static bool is_prov_root() {
    assert(__is_prov_root == 1 || __is_prov_root == 0);
    return __is_prov_root;
}
#endif

/*
 * exec-family of functions _rep\lace_ the process currently being run with a new process, by loading the specified program.
 * It has the same PID, but it is a new process.
 * Therefore, we track the "exec epoch".
 * If this PID is the same as the one in the environment, this must be a new exec epoch of the same.
 * Otherwise, it must be a truly new process.
 */
static const unsigned int __exec_epoch_initial = UINT_MAX;
static unsigned int __exec_epoch = __exec_epoch_initial;
static void init_exec_epoch() {
    assert(__exec_epoch == __exec_epoch_initial);
    const char* tracee_pid_env_var = PRIVATE_ENV_VAR_PREFIX "TRACEE_PID";
    /* We will store EXEC_EPOCH_PLUS_ONE because 0 is a sentinel value for strtol. */
    const char* exec_epoch_plus_one_env_var = PRIVATE_ENV_VAR_PREFIX "EXEC_EPOCH_PLUS_ONE";
    const char* tracee_pid_str = debug_getenv(tracee_pid_env_var);
    const char* exec_epoch_plus_one_str = debug_getenv(exec_epoch_plus_one_env_var);
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
        char new_tracee_pid_str[unsigned_int_string_size];
        CHECK_SNPRINTF(new_tracee_pid_str, unsigned_int_string_size, "%u", new_tracee_pid);
        debug_setenv(tracee_pid_env_var, new_tracee_pid_str, true);
    }
    DEBUG("exec_epoch = %d", __exec_epoch);
    char new_exec_epoch_str[unsigned_int_string_size];
    CHECK_SNPRINTF(new_exec_epoch_str, unsigned_int_string_size, "%u", __exec_epoch + 2);
    debug_setenv(exec_epoch_plus_one_env_var, new_exec_epoch_str, true);
}
static unsigned int get_exec_epoch() {
    assert(__exec_epoch != __exec_epoch_initial);
    return __exec_epoch;
}
static unsigned int get_exec_epoch_safe() {
    return __exec_epoch;
}

/*
 * Linux can technically reuse PIDs.
 * It usually doesn't happen that much, but I use the process birth_time-time as a "last-resort" in case it does.
 * */
static const struct timespec __process_birth_time_initial = {-1, 0};
static struct timespec __process_birth_time = __process_birth_time_initial;
static bool init_process_birth_time() {
    assert(
        __process_birth_time.tv_sec == __process_birth_time_initial.tv_sec &&
        __process_birth_time.tv_nsec == __process_birth_time_initial.tv_nsec
    );
    const char* process_birth_time_env_var = PRIVATE_ENV_VAR_PREFIX "PROCESS_BIRTH_TIME";
    if (get_exec_epoch() == 0) {
        EXPECT(== 0, clock_gettime(CLOCK_REALTIME, &__process_birth_time));
        int process_birth_time_str_length = signed_long_string_size + unsigned_long_string_size + 1;
        char process_birth_time_str[process_birth_time_str_length];
        CHECK_SNPRINTF(process_birth_time_str, process_birth_time_str_length, "%ld.%ld", __process_birth_time.tv_sec, __process_birth_time.tv_nsec);
        debug_setenv(process_birth_time_env_var, process_birth_time_str, true);
        return true;
    } else {
        const char* process_birth_time_str = debug_getenv(process_birth_time_env_var);
        assert(process_birth_time_str);
        char* rest_of_str = NULL;
        __process_birth_time.tv_sec = strtol(process_birth_time_str, &rest_of_str, 10);
        assert(rest_of_str[0] == '.');
        rest_of_str++;
        __process_birth_time.tv_nsec = strtol(rest_of_str, NULL, 10);
        return false;
    }
}
static struct timespec get_process_birth_time() {
    assert(
        __process_birth_time.tv_sec != __process_birth_time_initial.tv_sec ||
        __process_birth_time.tv_nsec != __process_birth_time_initial.tv_nsec
    );
    return __process_birth_time;
}
/* I guess nobody needs a safe version of this. */

/*
 * Linux can reuse a TID after one dies.
 * This is a big problem for us, so we just have our own TIDs based on an atomic thread counter.
 * */
static _Atomic unsigned int __thread_counter = 0;
static const unsigned int __thread_id_initial = UINT_MAX;
static __thread unsigned int __thread_id = __thread_id_initial;
static void init_sams_thread_id() {
    assert(__thread_id == __thread_id_initial);
    __thread_id = __thread_counter++;
    DEBUG("thread_id = %d", __thread_id);
}
static unsigned int get_sams_thread_id() {
    assert(__thread_id != __thread_id_initial && __thread_id <= __thread_counter);
    return __thread_id;
}
static unsigned int get_sams_thread_id_safe() {
    return __thread_id;
}

/* TODO: Hack exec-family of functions to propagate these environment variables. */

static void init_process_global_state() {
    init_is_prov_root();
    init_process_id();
    init_exec_epoch();
    init_process_birth_time();
}

static void init_thread_global_state() {
    init_sams_thread_id();
}

/*
 * After a fork, the process will _appear_ to be initialized, but not be truly initialized.
 * E.g., process_id will be wrong.
 * Therefore, we will reset all the things and call init again.
 */
static void reinit_process_global_state() {
    __is_prov_root = 0;

    __process_id = __process_id_initial;
    init_process_id();

    __exec_epoch = __exec_epoch_initial;
    init_exec_epoch();
    assert(__exec_epoch == 0);
    /* We know that __exec_epoch should be 0.
     * But we still need to call init_exec_epoch because it sets environment variables for our children.
     * */

    __process_birth_time = __process_birth_time_initial;
    __attribute__((unused)) bool did_update_birth_time = init_process_birth_time();
    assert(did_update_birth_time);

    __thread_counter = 0;
}

static void reinit_thread_global_state() {
    __thread_id = 0;
}

static char* const* update_env_with_probe_vars(char* const* user_env) {
    /* Define env vars we care about */
    const char* probe_vars[5] = {
        PRIVATE_ENV_VAR_PREFIX "IS_ROOT",
        PRIVATE_ENV_VAR_PREFIX "TRACEE_PID",
        PRIVATE_ENV_VAR_PREFIX "EXEC_EPOCH_PLUS_ONE",
        PRIVATE_ENV_VAR_PREFIX "PROCESS_BIRTH_TIME",
        ENV_VAR_PREFIX "DIR",
    };
    const size_t probe_var_count = sizeof(probe_vars) / sizeof(char*);

    /* Precompute some shiz */
    size_t probe_var_lengths[5] = { 0 };
    for (size_t probe_var_i = 0; probe_var_i < probe_var_count; ++probe_var_i) {
        probe_var_lengths[probe_var_i] = strlen(probe_vars[probe_var_i]);
    }
    char* probe_entries[5] = { NULL };
    for (size_t probe_var_i = 0; probe_var_i < probe_var_count; ++probe_var_i) {
        for (char** ep = environ; *ep; ++ep) {
            if (strncmp(*ep, probe_vars[probe_var_i], probe_var_lengths[probe_var_i]) == 0 && (*ep)[probe_var_lengths[probe_var_i]] == '=') {
                probe_entries[probe_var_i] = *ep;
                break;
            }
        }
        ASSERTF(probe_entries[probe_var_i], "No env var %s found", probe_vars[probe_var_i]);
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
        for (size_t probe_var_i = 0; probe_var_i < probe_var_count; ++probe_var_i) {
            if (strncmp(*ep, probe_vars[probe_var_i], probe_var_lengths[probe_var_i]) == 0 && (*ep)[probe_var_lengths[probe_var_i]] == '=') {
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
    for (size_t probe_var_i = 0; probe_var_i < probe_var_count; ++probe_var_i) {
        new_env[new_env_size + probe_var_i] = probe_entries[probe_var_i];
    }

    /* Top it off with a NULL */
    new_env[new_env_size + probe_var_count] = NULL;
    return new_env;
}

static void printenv() {
/*
    for (char** arg = environ; *arg; ++arg) {
        DEBUG("%s", *arg);
    }
*/
}
