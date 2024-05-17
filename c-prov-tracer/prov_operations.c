typedef int32_t Fd;

struct Path {
    Fd dirfd_minus_at_fdcwd;
    const char* path;
    dev_t device_major;
    dev_t device_minor;
    ino_t inode;
};

static struct Path null_path = {-1, NULL, -20, -20, -20};

static struct Path create_path(int dirfd, BORROWED const char* path) {
    struct Path ret = {
        dirfd - AT_FDCWD,
        EXPECT_NONNULL(strndup(path, PATH_MAX)),
        -20,
        -20,
        -20,
    };

    /*
     * If dirfd == 0, then the user is asserting it is not needed.
     * Path must be absolute. */
    assert(dirfd != 0 || path[0] == '/');

    /*
     * if path == "", then the target is the dir specified by dirfd.
     * */
    struct stat stat_buf;
    int stat_ret;
    if (path[0] == '\0') {
        stat_ret = o_fstat(dirfd, &stat_buf);
    } else {
        stat_ret = o_fstatat(dirfd, path, &stat_buf, 0);
    }
    if (stat_ret == 0) {
        ret.device_major = major(stat_buf.st_dev);
        ret.device_minor = minor(stat_buf.st_dev);
        ret.inode = stat_buf.st_ino;
    }
    return ret;
}

static void free_path(struct Path path) {
    free((char*) path.path);
}

enum OpCode {
    FIRST_OP_CODE,
    init_process_op_code,
    init_thread_op_code,
    open_op_code,
    close_op_code,
    chdir_op_code,
    exec_op_code,
    clone_op_code,
    access_op_code,
    stat_op_code,
    chown_op_code,
    chmod_op_code,
    read_link_op_code,
    LAST_OP_CODE,
};

struct InitProcessOp {
    pid_t process_id;
    unsigned int exec_epoch;
    struct timespec process_birth_time;
    OWNED char* program_name;
};

static unsigned int __process_id = 0;
static void init_process_id() {
    __process_id = getpid();
}
static pid_t get_process_id() {
    return __process_id;
}

/*
 * we store exec_epoch + 1.
 * That way, 0 can be a sentinel value (never the true value).
 */
static unsigned int __exec_epoch = UINT_MAX;
static void init_exec_epoch() {
    /*
     * exec-family of functions _replace_ the process currently being run with a new process, by loading the specified program.
     * It has the same PID, but it is a new process.
     * Therefore, we track the "exec epoch".
     * If this PID is the same as the one in the environment, this must be a new exec epoch of the same.
     * Otherwise, it must be a truly new process.
     */
    assert(__exec_epoch == UINT_MAX);
    const char* tracee_pid_envvar = "__PROV_LOG_TRACE_PID";
    const char* exec_epoch_envvar = "__PROV_LOG_EXEC_EPOCH";
    char* tracee_pid_str = getenv(tracee_pid_envvar);
    char* exec_epoch_str = getenv(exec_epoch_envvar);
    pid_t tracee_pid = -1;
    assert((exec_epoch_str == NULL) == (exec_epoch_str == NULL));
    if (exec_epoch_str) {
        tracee_pid = (pid_t) EXPECT(> 0, strtol(tracee_pid_str, NULL, 10));
    }
    pid_t new_tracee_pid = get_process_id();
    __exec_epoch = 1;
    if (new_tracee_pid == tracee_pid) {
        __exec_epoch = (size_t) EXPECT(> 0, strtol(exec_epoch_str, NULL, 10));
        /*
         * We are one exec deeper than the last guy.
         */
        __exec_epoch++;
    } else {
        /* the default value of new_exec_epoch is correct here. */
    }
    char new_tracee_pid_str[unsigned_int_string_size];
    char new_exec_epoch_str[unsigned_int_string_size];
    CHECK_SNPRINTF(new_tracee_pid_str, unsigned_int_string_size, "%ud", new_tracee_pid);
    CHECK_SNPRINTF(new_exec_epoch_str, unsigned_int_string_size, "%ud", __exec_epoch);
    setenv(tracee_pid_envvar, new_tracee_pid_str, true);
    setenv(exec_epoch_envvar, new_exec_epoch_str, true);
}
static unsigned int get_exec_epoch() {
    return __exec_epoch;
}

static struct timespec __process_birth_time = {0, 0};
static void init_process_birth_time() {
    /*
     * Linux can technically reuse PIDs.
     * It usually doesn't happen that much, but I use the process birth_time-time as a "last-resort" in case it does.
     * */
    assert(__process_birth_time.tv_sec == 0 && __process_birth_time.tv_nsec == 0);
    EXPECT(== 0, clock_gettime(CLOCK_REALTIME, &__process_birth_time));
}
static struct timespec get_process_birth_time() {
    return __process_birth_time;
}

struct InitProcessOp init_current_process() {
    struct InitProcessOp ret = {
        .process_id = get_process_id(),
        .process_birth_time = get_process_birth_time(),
        .exec_epoch = get_exec_epoch(),
        .program_name = strndup("__progname doesn't work for some reason", PATH_MAX),
    };
    return ret;
}

struct InitThreadOp {
    pid_t process_id;
    struct timespec process_birth_time;
    unsigned int exec_epoch;
    pid_t sams_thread_id; /* Not the same as TID in Linux */
};

static _Atomic unsigned int __thread_counter = 0;
static __thread unsigned int __thread_id = UINT_MAX;
static void init_sams_thread_id() {
    /*
     * Linux can reuse a TID after one dies.
     * This is a big problem for us, so we just have our own TIDs based on an atomic thread counter.
     * */
    assert(__thread_id == UINT_MAX);
    __thread_id = __thread_counter++;
}
static unsigned int get_sams_thread_id() {
    return __thread_id;
}

static struct InitThreadOp init_current_thread() {
    struct InitThreadOp ret = {
        .process_id = get_process_id(),
        .process_birth_time = get_process_birth_time(),
        .exec_epoch = get_exec_epoch(),
        .sams_thread_id = get_sams_thread_id(),
    };
    return ret;
}

static int fopen_to_flags(BORROWED const char* fopentype) {
    /* Table from fopen to open is documented here:
     * https://www.man7.org/linux/man-pages/man3/fopen.3.html
     **/
    bool plus = fopentype[1] == '+' || (fopentype[1] != '\0' && fopentype[2] == '+');
    if (false) {
    } else if (fopentype[0] == 'r' && !plus) {
        return O_RDONLY;
    } else if (fopentype[0] == 'r' && plus) {
        return O_RDWR;
    } else if (fopentype[0] == 'w' && !plus) {
        return O_WRONLY | O_CREAT | O_TRUNC;
    } else if (fopentype[0] == 'w' && plus) {
        return O_RDWR | O_CREAT | O_TRUNC;
    } else if (fopentype[0] == 'a' && !plus) {
        return O_WRONLY | O_CREAT | O_APPEND;
    } else if (fopentype[0] == 'a' && plus) {
        return O_RDWR | O_CREAT | O_APPEND;
    } else {
        NOT_IMPLEMENTED("Unknown fopentype %s", fopentype);
    }
}

struct OpenOp {
    struct Path path;
    int flags;
    mode_t mode;
    Fd fd;
    int ferrno;
};

struct CloseOp {
    Fd low_fd;
    Fd high_fd;
    int ferrno;
};

struct ChdirOp {
    struct Path path;
    int ferrno;
};

struct ExecOp {
    struct Path path;
    int ferrno;
};

struct CloneOp {
    int flags;
    bool run_pthread_atfork_handlers;
    pid_t child_process_id;
    pid_t child_thread_id;
    int ferrno;
};

struct AccessOp {
    struct Path path;
    mode_t mode;
    int flags;
    int ferrno;
};

struct StatOp {
    struct Path path;
    int flags;
    int mask;
    struct statx statx_buf;
    int ferrno;
};

struct ChownOp {
    struct Path path;
    uid_t uid;
    gid_t gid;
    int ferrno;
};

struct ChmodOp {
    struct Path path;
    mode_t mode;
    int ferrno;
};

struct ReadLinkOp {
    struct Path path;
    const char* resolved;
    int ferrno;
};

struct Op {
    enum OpCode op_code;
    union {
        struct InitProcessOp init_process;
        struct InitThreadOp init_thread;
        struct OpenOp open;
        struct CloseOp close;
        struct ChdirOp chdir;
        struct ExecOp exec;
        struct CloneOp clone;
        struct AccessOp access;
        struct StatOp stat;
        struct ChownOp chown;
        struct ChmodOp chmod;
        struct ReadLinkOp read_link;
    } data;
};

static void free_op(struct Op op) {
    switch (op.op_code) {
        case open_op_code: free_path(op.data.open.path); break;
        case init_process_op_code: free(op.data.init_process.program_name); break;
        case exec_op_code: free_path(op.data.exec.path); break;
        case access_op_code: free_path(op.data.access.path); break;
        case stat_op_code: free_path(op.data.stat.path); break;
        case chown_op_code: free_path(op.data.chown.path); break;
        case chmod_op_code: free_path(op.data.chmod.path); break;
        case read_link_op_code:
            free_path(op.data.read_link.path);
            free((char*) op.data.read_link.resolved);
            break;
        default:
    }
}

static BORROWED const char* op_code_to_string(enum OpCode op_code) {
    switch (op_code) {
        case init_process_op_code: return "init_process";
        case init_thread_op_code: return "init_thread";
        case open_op_code: return "open";
        case close_op_code: return "close";
        case chdir_op_code: return "chdir";
        case exec_op_code: return "exec";
        case access_op_code: return "access";
        case stat_op_code: return "stat";
        case chown_op_code: return "chown";
        case chmod_op_code: return "chmod";
        case read_link_op_code: return "read_link";
        default:
            ASSERTF(op_code <= FIRST_OP_CODE || op_code >= LAST_OP_CODE, "Not a valid op_code: %d", op_code);
            NOT_IMPLEMENTED("op_code %d is valid, but not handled", op_code);
    }
}

static void write_op(int fd, struct Op op) {
    EXPECT( > 0, write(fd, (void*) &op, sizeof(op)));
}
