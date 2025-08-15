#define _GNU_SOURCE
#include "global_state.h"

#include <fcntl.h>     // for AT_FDCWD, O_CREAT, O_PATH, O_RD...
#include <limits.h>    // IWYU pragma: keep for PATH_MAX
#include <pthread.h>   // for pthread_mutex_t
#include <stdbool.h>   // for true, bool, false
#include <stdlib.h>    // for free
#include <string.h>    // for memcpy, NULL, size_t, strnlen// for memcpy, NULL, size_t, strnlen
#include <sys/mman.h>  // for mmap, PROT_*, MAP_*
#include <sys/stat.h>  // IWYU pragma: keep for STATX_BASIC_STATS, statx
#include <sys/types.h> // for pid_t
#include <unistd.h>    // for getpid, gettid, confstr, _CS_PATH
// IWYU pragma: no_include "bits/mman-linux.h"    for PROT_*
// IWYU pragma: no_include "bits/pthreadtypes.h"  for pthread_mutex_t
// IWYU pragma: no_include "linux/limits.h"       for PATH_MAX
// IWYU pragma: no_include "linux/stat.h"         for STATX_BASIC_STATS, statx

#include "../generated/bindings.h"        // for FixedPath, ProcessContext, PIDS...
#include "../generated/libc_hooks.h"      // for client_mkdirat, client_close
#include "../include/libprobe/prov_ops.h" // for OpCode, StatResult, Op
#include "arena.h"                        // for arena_is_initialized, arena_create
#include "debug_logging.h"                // for ASSERTF, EXPECT, DEBUG, ERROR
#include "env.h"                          // for getenv_copy
#include "inode_table.h"                  // for inode_table_init, inode_table_i...
#include "prov_buffer.h"                  // for prov_log_try, prov_log_record, prov_log_save
#include "prov_utils.h"                   // for do_init_ops
#include "util.h"                         // for CHECK_SNPRINTF, list_dir, UNLIKELY

#ifdef NDEBUG
#define check_fixed_path(path)
#else
#define check_fixed_path(path)                                                                     \
    ({                                                                                             \
        ASSERTF((path)->len > 2, "{\"%s\", %d}", (path)->bytes, (path)->len);                      \
        ASSERTF((path)->bytes[0] == '/', "{\"%s\", %d}", (path)->bytes, (path)->len);              \
        ASSERTF((path)->bytes[(path)->len - 1] != '\0', "{\"%s\", %d}", (path)->bytes,             \
                (path)->len);                                                                      \
        ASSERTF((path)->bytes[(path)->len] == '\0', "{\"%s\", %d}", (path)->bytes, (path)->len);   \
    })
#endif

void copy_string_to_fixed_path(struct FixedPath* path, const char* string) {
    size_t str_len = strnlen(string, PATH_MAX);
    memcpy(&path->bytes, string, str_len);
    path->len = str_len;
    check_fixed_path(path);
}

// Use a macro so we get the location of the callee in the dbeug log
#define checked_mkdir(path)                                                                        \
    ({                                                                                             \
        DEBUG("mkdir '%s'", path);                                                                 \
        int mkdir_ret = client_mkdirat(AT_FDCWD, path, 0777);                                      \
        if (mkdir_ret == -1) {                                                                     \
            list_dir(path, 2);                                                                     \
            ERROR("Could not mkdir directory '%s'", path);                                         \
        }                                                                                          \
    })

static inline void* open_and_mmap(const char* path, bool writable, size_t size) {
    DEBUG("mapping path = \"%s\"; size=%ld; writable=%d", path, size, writable);
    int fd = client_openat(AT_FDCWD, path, (writable ? (O_RDWR | O_CREAT) : O_RDONLY), 0777);
    if (UNLIKELY(fd == -1)) {
        ERROR("Could not open file at %s", path);
    }
    if (writable) {
        EXPECT(== 0, client_ftruncate(fd, size));
    }
    void* ret = EXPECT_NONNULL(client_mmap(
        NULL, size, (writable ? (PROT_READ | PROT_WRITE) : PROT_READ), MAP_SHARED, fd, 0));
    ASSERTF(ret != MAP_FAILED, "mmap did not succeed");
    EXPECT(== 0, client_close(fd));
    return ret;
}

/*
 * The rest of these variables are set up by ELF constructor.
 * Within one epoch, pointers are valid.
 */
static struct FixedPath __probe_dir = {0};
static inline void init_probe_dir() {
    ASSERTF(__probe_dir.bytes[0] == '\0', "__probe_dir already initialized");
    const char* __probe_private_dir_env_val = getenv_copy(PROBE_DIR_VAR);
    if (UNLIKELY(!__probe_private_dir_env_val)) {
        ERROR("env " PROBE_DIR_VAR " is not set");
    }
    copy_string_to_fixed_path(&__probe_dir, __probe_private_dir_env_val);
}
const struct FixedPath* get_probe_dir() {
    check_fixed_path((&__probe_dir));
    return &__probe_dir;
}

static pid_t __pid = 0;
static inline void init_pid(bool after_fork) {
    (void)after_fork;
    ASSERTF(!!__pid == after_fork, "__pid=%d, after_fork=%d", __pid, after_fork);
    pid_t tmp = getpid();
    ASSERTF(!after_fork || __pid != tmp,
            "If after_fork, old __pid (%d) should not be equal to new (actual) pid (%d).", __pid,
            tmp);
    __pid = tmp;
}

pid_t get_pid() { return EXPECT(!= 0, __pid); }
pid_t get_pid_safe() { return getpid(); }

static struct InodeTable __read_inodes;
static struct InodeTable __copied_or_overwritten_inodes;
static inline void init_tables() {
    ASSERTF(!inode_table_is_init(&__read_inodes), "");
    ASSERTF(!inode_table_is_init(&__copied_or_overwritten_inodes), "");
    inode_table_init(&__read_inodes);
    inode_table_init(&__copied_or_overwritten_inodes);
}
struct InodeTable* get_read_inodes() {
    ASSERTF(inode_table_is_init(&__read_inodes), "");
    return &__read_inodes;
}
struct InodeTable* get_copied_or_overwritten_inodes() {
    ASSERTF(inode_table_is_init(&__copied_or_overwritten_inodes), "");
    return &__copied_or_overwritten_inodes;
}

/*
 * Set up by CLI.
 * Use probe_dir to find and mmap this.
 */
static struct ProcessTreeContext* __process_tree_context = NULL;
static inline void init_process_tree_context() {
    const struct FixedPath* probe_dir = get_probe_dir();
    char path_buf[PATH_MAX] = {0};
    memcpy(path_buf, probe_dir->bytes, probe_dir->len);

    /* Set up process tree context
     * Note that sizeof("abc") already includes 1 extra for the null byte. */
    memcpy(path_buf + probe_dir->len, "/" PROCESS_TREE_CONTEXT_FILE "\0",
           (sizeof(PROCESS_TREE_CONTEXT_FILE) + 1));
    __process_tree_context = open_and_mmap(path_buf, false, sizeof(struct ProcessTreeContext));
}
static inline const struct ProcessTreeContext* get_process_tree_context() {
    ASSERTF(__process_tree_context != NULL, "");
    return __process_tree_context;
}

/*
 * Set up by CLI or previous epoch.
 * use probe_dir and pid to find this.
 */
static struct ProcessContext* __process_context = NULL;
static inline void init_process_context() {
    const struct FixedPath* probe_dir = get_probe_dir();
    char path_buf[PATH_MAX] = {0};
    /* Set up process context */
    memcpy(path_buf, probe_dir->bytes, probe_dir->len);
    CHECK_SNPRINTF(path_buf + probe_dir->len, (int)(PATH_MAX - probe_dir->len),
                   "/" CONTEXT_SUBDIR "/%d", __pid);
    __process_context = open_and_mmap(path_buf, true, sizeof(struct ProcessContext));
    /* We increment the epoch here, so if there is an exec later on, the epoch is already incremented when they see it. */
    __process_context->epoch_no += 1;
    DEBUG("__process_context = %p {.epoch = %d, pid_arena_path = %s}", __process_context,
          __process_context->epoch_no, __process_context->pid_arena_path.bytes);
}
void uninit_process_context() {
    /* TODO: */
    /* client_munmap(__process_context, sizeof(struct ProcessContext)); */
}
static inline const struct ProcessContext* get_process_context() {
    return EXPECT_NONNULL(__process_context);
}
ExecEpoch get_exec_epoch() { return get_process_context()->epoch_no - 1; }
ExecEpoch get_exec_epoch_safe() {
    if (__process_context) {
        return __process_context->epoch_no - 1;
    } else {
        return 0;
    }
}
static inline bool is_first_epoch() { return get_exec_epoch() == 0; }
const struct FixedPath* get_libprobe_path() { return &(get_process_tree_context()->libprobe_path); }
enum CopyFiles get_copy_files_mode() { return get_process_tree_context()->copy_files; }

static inline void create_epoch_dir() {
    char path_buf[PATH_MAX] = {0};
    const struct FixedPath* probe_dir = get_probe_dir();
    memcpy(path_buf, probe_dir->bytes, probe_dir->len);

    /* mkdir epoch */
    if (is_first_epoch()) {
        DEBUG("First epoch");
        /* mkdir process dirs */
        CHECK_SNPRINTF(path_buf + probe_dir->len, (int)(PATH_MAX - probe_dir->len),
                       "/" PIDS_SUBDIR "/%d", __pid);
        checked_mkdir(path_buf);
    }
    CHECK_SNPRINTF(path_buf + probe_dir->len, (int)(PATH_MAX - probe_dir->len),
                   "/" PIDS_SUBDIR "/%d/%d", __pid, __process_context->epoch_no - 1);
    checked_mkdir(path_buf);
}

static struct FixedPath __default_path;
static inline void init_default_path() {
    ASSERTF(__default_path.bytes[0] == '\0', "__default_path already initialized");
    __default_path.len = EXPECT(!= 0, confstr(_CS_PATH, __default_path.bytes, PATH_MAX));
}
const char* get_default_path() {
    ASSERTF(__default_path.bytes[0] != '\0', "");
    return __default_path.bytes;
}

static PthreadID __pthread_id_counter = 1;

void free_thread_state(void* arg);

static pthread_key_t __thread_state_key;
static inline void init_thread_state_key() {
    EXPECT(== 0, pthread_key_create(&__thread_state_key, free_thread_state));
}

struct ThreadState {
    pid_t tid;
    PthreadID pthread_id;
    struct FixedPath ops_path;
    struct FixedPath data_path;
    struct ArenaDir ops_arena;
    struct ArenaDir data_arena;
};
/* pthread_getspecific is how one should access the _current thread's_ state.
 * (*thread_table[upper_8_bits_of_pthread_id])[[lower_8_bits_of_pthread_id]] is how one should access _another thread's_ state. */
typedef struct ThreadState* ThreadTable1[256];
typedef ThreadTable1* ThreadTable0[256];
ThreadTable0 __thread_table = {NULL};
static inline void init_tid(struct ThreadState* state) { state->tid = gettid(); }
PthreadID increment_pthread_id() {
    return __atomic_add_fetch(&__pthread_id_counter, 1, __ATOMIC_RELAXED);
}
static const size_t prov_log_arena_size = 64 * 1024;
static inline void init_paths(struct ThreadState* state) {
    const struct FixedPath* probe_dir = get_probe_dir();
    pid_t pid = get_pid();
    size_t exec_epoch = get_exec_epoch();
    state->ops_path.len =
        CHECK_SNPRINTF(state->ops_path.bytes, PATH_MAX, "%s/" PIDS_SUBDIR "/%d/%zu/%d",
                       probe_dir->bytes, pid, exec_epoch, state->tid);
    check_fixed_path((&state->ops_path));
    checked_mkdir(state->ops_path.bytes);

    state->ops_path.len = CHECK_SNPRINTF(state->ops_path.bytes, PATH_MAX,
                                         "%s/" PIDS_SUBDIR "/%d/%zu/%d/" OPS_SUBDIR "/",
                                         probe_dir->bytes, pid, exec_epoch, state->tid);
    check_fixed_path((&state->ops_path));

    state->data_path.len = CHECK_SNPRINTF(state->data_path.bytes, PATH_MAX,
                                          "%s/" PIDS_SUBDIR "/%d/%zu/%d/" DATA_SUBDIR "/",
                                          probe_dir->bytes, pid, exec_epoch, state->tid);
    check_fixed_path((&state->data_path));
}
static inline void init_arenas(struct ThreadState* state) {
    arena_create(&state->ops_arena, state->ops_path.bytes, state->ops_path.len, PATH_MAX,
                 prov_log_arena_size);
    arena_create(&state->data_arena, state->data_path.bytes, state->data_path.len, PATH_MAX,
                 prov_log_arena_size);
    ASSERTF(arena_is_initialized(&state->ops_arena), "");
    ASSERTF(arena_is_initialized(&state->data_arena), "");
}
static inline struct ThreadState* get_thread_state() {
    return EXPECT_NONNULL(pthread_getspecific(__thread_state_key));
}
void free_thread_state(void* arg) {
    struct ThreadState* state = EXPECT_NONNULL(arg);
    /* TODO: Insert exit op */
    arena_sync(&state->data_arena);
    arena_sync(&state->ops_arena);
    free(state);
}
static inline void init_thread_state(PthreadID pthread_id) {
    struct ThreadState* state = EXPECT_NONNULL(malloc(sizeof(struct ThreadState)));
    init_tid(state);
    state->pthread_id = pthread_id;
    init_paths(state);
    init_arenas(state);
    ASSERTF(pthread_getspecific(__thread_state_key) == NULL,
            "pthread threadstate key already used");
    EXPECT(== 0, pthread_setspecific(__thread_state_key, state));
    uint8_t pthread_id_level0 = (state->pthread_id & 0xFF00) >> 8;
    uint8_t pthread_id_level1 = (state->pthread_id & 0x00FF);
    if (!__thread_table[pthread_id_level0]) {
        __thread_table[pthread_id_level0] = EXPECT_NONNULL(malloc(sizeof(ThreadTable1)));
    }
    ThreadTable1* level1 = __thread_table[pthread_id_level0];
    ASSERTF(!(*level1)[pthread_id_level1], "ThreadTable at %d (%d << 8 | %d) already occupied",
            state->pthread_id, pthread_id_level0, pthread_id_level1);
    (*level1)[pthread_id_level1] = state;
}
static inline void drop_threads_after_fork() {
    for (PthreadID pthread_id = 0; pthread_id < __pthread_id_counter; ++pthread_id) {
        uint8_t pthread_id_level0 = (pthread_id & 0xFF00) >> 8;
        uint8_t pthread_id_level1 = (pthread_id & 0x00FF);
        ThreadTable1* level1 = EXPECT_NONNULL(__thread_table[pthread_id_level0]);
        struct ThreadState* state = EXPECT_NONNULL((*level1)[pthread_id_level1]);
        arena_drop_after_fork(&state->data_arena);
        arena_drop_after_fork(&state->ops_arena);
        free(state);
        (*__thread_table[pthread_id_level0])[pthread_id_level1] = NULL;
        /* We free the actual ThreadState and NULL out the dangling pointer.
         * I guess we'll leave __thread_table[pthread_id_level0] allocated.
         * If the parent process had N threads, that's a damn decent guess of how many threads the child will have.
         * Consider it "pre-allocation". */
    }
    __pthread_id_counter = 1;
}
struct ArenaDir* get_op_arena() { return &(get_thread_state()->ops_arena); }
struct ArenaDir* get_data_arena() { return &(get_thread_state()->data_arena); }
pid_t get_tid() { return get_thread_state()->tid; }
pid_t get_tid_safe() { return gettid(); }
PthreadID get_pthread_id() { return get_thread_state()->pthread_id; }

static inline void check_function_pointers() {
#ifndef NDEBUG
    /* We use these client_ function pointers in our code.
     * The rest of the client_ function pointers are only used if the application (tracee) calls the corresponding libc (without client_ prefix) function.
     * */
    ASSERTF(client_close, "");
    ASSERTF(client_execvpe, "");
    ASSERTF(client_faccessat, "");
    ASSERTF(client_fcntl, "");
    ASSERTF(client_fexecve, "");
    ASSERTF(client_fork, "");
    ASSERTF(client_ftruncate, "");
    ASSERTF(client_mkdirat, "");
    ASSERTF(client_mmap, "");
    ASSERTF(client_munmap, "");
    ASSERTF(client_openat, "");
    ASSERTF(client_statx, "");

    // assert that function pointers are callable
    struct statx buf;
    EXPECT(== 0, client_statx(AT_FDCWD, ".", 0, STATX_BASIC_STATS, &buf));
    int fd = EXPECT(> 0, client_openat(AT_FDCWD, ".", O_PATH));
    EXPECT(== 0, client_close(fd));
#endif
}

static inline void emit_init_epoch_op() {
    static struct FixedPath cwd = {0};
    static struct FixedPath exe = {0};
    if (!getcwd(cwd.bytes, PROBE_PATH_MAX)) {
        ERROR("");
    }
    if (client_readlinkat(AT_FDCWD, "/proc/self/exe", exe.bytes, PROBE_PATH_MAX) < 0) {
        ERROR("");
    }
    size_t argc = 0;
    size_t envc = 0;
    char* const* argv = read_null_delim_file("/proc/self/cmdline", &argc);
    char* const* env = read_null_delim_file("/proc/self/environ", &envc);
    struct Op init_epoch_op = {
        init_exec_epoch_op_code,
        {.init_exec_epoch =
             {
                 .parent_pid = getppid(),
                 .pid = getpid(),
                 .epoch = get_exec_epoch(),
                 .cwd = create_path_lazy(AT_FDCWD, cwd.bytes, 0),
                 .exe = create_path_lazy(AT_FDCWD, exe.bytes, 0),
                 .argv = arena_copy_argv(get_data_arena(), argv, argc),
                 .env = arena_copy_argv(get_data_arena(), env, envc),
                 .std_in = create_path_lazy(AT_FDCWD, "/dev/stdin", 0),
                 .std_out = create_path_lazy(AT_FDCWD, "/dev/stdout", 0),
                 .std_err = create_path_lazy(AT_FDCWD, "/dev/stderr", 0),
             }},
        {0},
        0,
        0,
    };
    prov_log_try(init_epoch_op);
    prov_log_record(init_epoch_op);
    free((void*)argv[0]);
    free((void*)argv);
    free((void*)env[0]);
    free((void*)env);
}

static inline void emit_init_thread_op() {
    struct Op init_thread_op = {
        init_thread_op_code, {.init_thread = {.tid = get_tid()}}, {0}, 0, 0,
    };
    prov_log_try(init_thread_op);
    prov_log_record(init_thread_op);
}

bool is_thread_inited() { return !!pthread_getspecific(__thread_state_key); }

bool is_proc_inited() {
    /* On forks, the PID will be changed from the parent,
     * "resetting" the iniialization status. */
    return getpid() == __pid;
}

void init_thread(PthreadID pthread_id) {
    ASSERTF(is_proc_inited(), "Process not inited");
    init_thread_state(pthread_id);
    emit_init_thread_op();
    ASSERTF(is_thread_inited(), "Failed to init thread");
}
void maybe_init_thread() { ASSERTF(is_thread_inited(), "Failed to init thread"); }

void save_atexit() {
    /* It seems pthread_getspecific is not valid atexit */
    /* prov_log_save(); */
}

void init_after_fork() {
    ASSERTF(!is_proc_inited(), "Proccess already initialized");
    ASSERTF(__pid != 0, "Parent process not initialized");
    check_function_pointers();
    init_pid(true);
    uninit_process_context();
    init_process_context();
    create_epoch_dir();
    init_thread_state_key();
    drop_threads_after_fork();
    init_thread_state(0);
    EXPECT(== 0, pthread_atfork(NULL, NULL, &init_after_fork));
    EXPECT(== 0, atexit(&save_atexit));
    ASSERTF(is_proc_inited(), "Failed to init proc");
    ASSERTF(is_thread_inited(), "Failed to init thread");
    emit_init_epoch_op();
    emit_init_thread_op();
}

void ensure_thread_initted() {
    ASSERTF(is_proc_inited(), "Process not initialized");
    ASSERTF(is_thread_inited(), "Thread not initialized");
}

__attribute__((constructor)) void constructor() {
    DEBUG("Initializing exec epoch");
    ASSERTF(!is_proc_inited(), "Proccess already initialized");
    init_function_pointers();
    check_function_pointers();
    init_pid(false);
    init_probe_dir();
    init_tables();
    init_process_tree_context();
    init_process_context();
    create_epoch_dir();
    init_default_path();
    init_thread_state_key();
    init_thread_state(0);
    EXPECT(== 0, pthread_atfork(NULL, NULL, &init_after_fork));
    EXPECT(== 0, atexit(&save_atexit));
    ASSERTF(is_proc_inited(), "Failed to init proc");
    ASSERTF(is_thread_inited(), "Failed to init thread");
    emit_init_epoch_op();
    emit_init_thread_op();
}
