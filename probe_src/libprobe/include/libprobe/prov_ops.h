struct Path {
    int32_t dirfd_minus_at_fdcwd;
    const char* path; /* path valid if non-null */
    dev_t device_major;
    dev_t device_minor;
    ino_t inode;
    struct statx_timestamp mtime;
    struct statx_timestamp ctime;
    bool stat_valid;
    bool dirfd_valid;
};

static const struct Path null_path = {-1, NULL, -1, -1, -1, {0}, {0}, false, false};
/* We don't need to free paths since I switched to the Arena allocator */
/* static void free_path(struct Path path); */

struct InitProcessOp {
    pid_t pid;
};

struct InitExecEpochOp {
    unsigned int epoch;
    OWNED char* program_name;
};

struct InitExecEpochOp init_current_exec_epoch();

struct InitThreadOp {
    pid_t tid;
};

struct OpenOp {
    struct Path path;
    int flags;
    mode_t mode;
    int32_t fd;
    int ferrno;
    /* Note, we use ferrno in these structs because errno is something magical (maybe a macro?) */
};

struct CloseOp {
    int32_t low_fd;
    int32_t high_fd;
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

enum TaskType {
    TASK_PID,
    TASK_TID,
    TASK_ISO_C_THREAD,
    TASK_PTHREAD,
};

struct CloneOp {
    int flags;
    bool run_pthread_atfork_handlers;
    enum TaskType task_type;
    unsigned long int task_id;
    int ferrno;
};

struct ExitOp {
    int status;
    bool run_atexit_handlers;
};

struct AccessOp {
    struct Path path;
    int mode;
    int flags;
    int ferrno;
};

struct StatOp {
    struct Path path;
    int flags;
    struct statx statx_buf;
    int ferrno;
};

struct ReaddirOp {
    struct Path dir;
    char* child;
    bool all_children;
    int ferrno;
};

struct WaitOp {
    enum TaskType task_type;
    unsigned long int task_id;
    int options;
    int status;
    int ferrno;
};

struct GetRUsageOp {
    pid_t waitpid_arg;
    int getrusage_arg;
    struct rusage usage;
    int ferrno;
};

enum MetadataKind {
    MetadataMode,
    MetadataOwnership,
    MetadataTimes,
};

union MetadataValue {
    mode_t mode;
    struct {
        uid_t uid;
        gid_t gid;
    } ownership;
    struct {
        bool is_null;
        struct timeval atime;
        struct timeval mtime;
    } times;
};

struct UpdateMetadataOp {
    struct Path path;
    int flags;
    enum MetadataKind kind;
    union MetadataValue value;
    int ferrno;
};

struct ReadLinkOp {
    struct Path path;
    const char* resolved;
    int ferrno;
};

enum OpCode {
    FIRST_OP_CODE,
    init_process_op_code,
    init_exec_epoch_op_code,
    init_thread_op_code,
    open_op_code,
    close_op_code,
    chdir_op_code,
    exec_op_code,
    clone_op_code,
    exit_op_code,
    access_op_code,
    stat_op_code,
    readdir_op_code,
    wait_op_code,
    getrusage_op_code,
    update_metadata_op_code,
    read_link_op_code,
    LAST_OP_CODE,
};

struct Op {
    enum OpCode op_code;
    union {
        struct InitProcessOp init_process;
        struct InitExecEpochOp init_exec_epoch;
        struct InitThreadOp init_thread;
        struct OpenOp open;
        struct CloseOp close;
        struct ChdirOp chdir;
        struct ExecOp exec;
        struct CloneOp clone;
        struct ExitOp exit;
        struct AccessOp access;
        struct StatOp stat;
        struct ReaddirOp readdir;
        struct WaitOp wait;
        struct GetRUsageOp getrusage;
        struct UpdateMetadataOp update_metadata;
        struct ReadLinkOp read_link;
    } data;
    struct timespec time;
    pthread_t pthread_id;
    thrd_t iso_c_thread_id;
};

/* We don't need this since we switched to an Arena allocator */
/* static void free_op(struct Op op); */
