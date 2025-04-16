#define _GNU_SOURCE

#include "../generated/libc_hooks.h"
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "../generated/bindings.h"
#include "arena.h"
#include "env.h"
#include "inode_table.h"
#include "prov_buffer.h"
#include "prov_utils.h"
#include "util.h"

#include "global_state.h"

// getpid/gettid is kind of expensive (40ns per syscall)
// but worth it for debug case

static const pid_t pid_initial = -1;
static pid_t pid = pid_initial;
pid_t get_pid() { return EXPECT(== getpid(), pid); }
static inline void init_pid() { pid = EXPECT(!= pid_initial, getpid()); }
pid_t get_pid_safe() {
#ifdef NDEBUG
    return pid;
#else
    return getpid();
#endif
}

static const pid_t tid_initial = -1;
static __thread pid_t tid = tid_initial;
pid_t get_tid() { return EXPECT(== gettid(), tid); }
static inline void init_tid() { tid = EXPECT(!= tid_initial, gettid()); }
pid_t get_tid_safe() {
#ifdef NDEBUG
    return tid;
#else
    return gettid();
#endif
}

static inline void* open_and_mmap(const char* path, bool writable, size_t size) {
    DEBUG("mapping path = \"%s\"; size=%ld; writable=%d", path, size, writable);
    int fd = unwrapped_openat(AT_FDCWD, path, (writable ? (O_RDWR | O_CREAT) : O_RDONLY));
    if (UNLIKELY(fd == -1)) {
        ERROR("Could not open process_tree in parent's dir at %s", path);
    }
    if (writable) {
        EXPECT(== 0, unwrapped_ftruncate(fd, size));
    }
    void* ret = EXPECT_NONNULL(unwrapped_mmap(
        NULL, size, (writable ? (PROT_READ | PROT_WRITE) : PROT_READ), MAP_SHARED, fd, 0));
    ASSERTF(ret != MAP_FAILED, "mmap did not succeed");
    EXPECT(== 0, unwrapped_close(fd));
    DEBUG("ret = %p", ret);
    return ret;
}

static inline void checked_mkdir(const char* path) {
    int mkdir_ret = unwrapped_mkdirat(AT_FDCWD, path, 0777);
    if (mkdir_ret == -1) {
        ERROR("Could not open process directory at %s", path);
    }
}

static inline void check_fixed_path(
#ifdef NDEBUG
    __attribute__((unused))
#endif
    const struct FixedPath* path) {
    ASSERTF(path->len > 2, "{\"%s\", %d}", path->bytes, path->len);
    ASSERTF(path->bytes[0] == '/', "{\"%s\", %d}", path->bytes, path->len);
    ASSERTF(path->bytes[path->len - 1] != '\0', "{\"%s\", %d}", path->bytes, path->len);
    ASSERTF(path->bytes[path->len] == '\0', "{\"%s\", %d}", path->bytes, path->len);
}

static struct FixedPath __probe_dir = {0};
static inline void init_probe_dir() {
    const char* __probe_private_dir_env_val = getenv_copy(PROBE_DIR_VAR);
    if (UNLIKELY(!__probe_private_dir_env_val)) {
        ERROR("env " PROBE_DIR_VAR " is not set");
    }
    size_t probe_dir_len = strnlen(__probe_private_dir_env_val, PATH_MAX);
    memcpy(&__probe_dir.bytes, __probe_private_dir_env_val, probe_dir_len);
    __probe_dir.len = probe_dir_len;
    check_fixed_path(&__probe_dir);
}
const struct FixedPath* get_probe_dir() {
    check_fixed_path(&__probe_dir);
    return &__probe_dir;
}
static __thread struct FixedPath __probe_dir_thread;
void init_mut_probe_dir() {
    memcpy(__probe_dir_thread.bytes, __probe_dir.bytes, __probe_dir.len);
    __probe_dir_thread.len = __probe_dir.len;
    check_fixed_path(&__probe_dir_thread);
}
struct FixedPath* get_mut_probe_dir() {
    check_fixed_path(&__probe_dir_thread);
    return &__probe_dir_thread;
}

static struct ProcessContext* __process = NULL;
static const struct ProcessTreeContext* __process_tree = NULL;
static inline void init_process_obj() {
    const struct FixedPath* probe_dir = get_probe_dir();
    char path_buf[PATH_MAX] = {0};
    memcpy(path_buf, probe_dir->bytes, probe_dir->len);

    /* Set up process tree context
     * Note that sizeof("abc") already includes 1 extra for the null byte. */
    memcpy(path_buf + probe_dir->len, "/" PROCESS_TREE_CONTEXT_FILE "\0",
           (sizeof(PROCESS_TREE_CONTEXT_FILE) + 1));
    __process_tree = open_and_mmap(path_buf, false, sizeof(struct ProcessTreeContext));

    /* Set up process context */
    CHECK_SNPRINTF(path_buf + probe_dir->len, (int)(PATH_MAX - probe_dir->len),
                   "/" CONTEXT_SUBDIR "/%d", pid);
    __process = open_and_mmap(path_buf, true, sizeof(struct ProcessContext));
    if (__process->epoch_no == 0) {
        /* mkdir process dirs */
        CHECK_SNPRINTF(path_buf + probe_dir->len, (int)(PATH_MAX - probe_dir->len),
                       "/" PIDS_SUBDIR "/%d", pid);
        checked_mkdir(path_buf);
    } else {
        __process->epoch_no += 1;
    }

    /* mkdir epoch */
    CHECK_SNPRINTF(path_buf + probe_dir->len, (int)(PATH_MAX - probe_dir->len),
                   "/" PIDS_SUBDIR "/%d/%d", pid, __process->epoch_no);
    checked_mkdir(path_buf);
}
static inline const struct ProcessContext* get_process() { return EXPECT_NONNULL(__process); }
static inline const struct ProcessTreeContext* get_process_tree() {
    ASSERTF(__process_tree != NULL, "");
    return __process_tree;
}
const struct FixedPath* get_libprobe_path() { return &get_process_tree()->libprobe_path; }
enum CopyFiles get_copy_files_mode() { return get_process_tree()->copy_files; }

static struct InodeTable read_inodes;
static struct InodeTable copied_or_overwritten_inodes;

struct InodeTable* get_read_inodes() {
    ASSERTF(inode_table_is_init(&read_inodes), "");
    return &read_inodes;
}
struct InodeTable* get_copied_or_overwritten_inodes() {
    ASSERTF(inode_table_is_init(&copied_or_overwritten_inodes), "");
    return &copied_or_overwritten_inodes;
}

int get_exec_epoch_safe() {
    if (__process) {
        return __process->epoch_no;
    } else {
        return -1;
    }
}
int get_exec_epoch() { return get_process()->epoch_no; }

static __thread struct FixedPath __ops_path = {0};
static __thread struct FixedPath __data_path = {0};
static __thread struct ArenaDir __ops_arena = {0};
static __thread struct ArenaDir __data_arena = {0};
static const size_t prov_log_arena_size = 64 * 1024;
static inline void init_log_arena() {
    const struct ProcessContext* process = get_process();
    const struct FixedPath* probe_dir = get_probe_dir();
    pid_t pid = get_pid();
    pid_t tid = get_tid();
    __ops_path.len = CHECK_SNPRINTF(__ops_path.bytes, PATH_MAX, "%s/" PIDS_SUBDIR "/%d/%d/%d",
                                    probe_dir->bytes, pid, process->epoch_no, tid);
    check_fixed_path(&__ops_path);
    checked_mkdir(__ops_path.bytes);
    __ops_path.len =
        CHECK_SNPRINTF(__ops_path.bytes, PATH_MAX, "%s/" PIDS_SUBDIR "/%d/%d/%d/" OPS_SUBDIR "/",
                       probe_dir->bytes, pid, process->epoch_no, tid);
    check_fixed_path(&__ops_path);
    __data_path.len =
        CHECK_SNPRINTF(__data_path.bytes, PATH_MAX, "%s/" PIDS_SUBDIR "/%d/%d/%d/" DATA_SUBDIR "/",
                       probe_dir->bytes, pid, process->epoch_no, tid);
    check_fixed_path(&__data_path);
    arena_create(&__ops_arena, __ops_path.bytes, __ops_path.len, PATH_MAX, prov_log_arena_size);
    arena_create(&__data_arena, __data_path.bytes, __data_path.len, PATH_MAX, prov_log_arena_size);
    ASSERTF(arena_is_initialized(&__ops_arena), "");
    ASSERTF(arena_is_initialized(&__data_arena), "");
}
struct ArenaDir* get_op_arena() {
    ASSERTF(arena_is_initialized(&__ops_arena), "init_log_arena() not called");
    return &__ops_arena;
}
struct ArenaDir* get_data_arena() {
    ASSERTF(arena_is_initialized(&__data_arena), "init_log_arena() not called");
    return &__data_arena;
}

/*
 * echo '#include <stdio.h>\n#include <unistd.h>\nint main() {printf("%ld\\n", confstr(_CS_PATH, NULL, 0)); return 0;}' | gcc -x c - && ./a.out && rm a.out
 */
static struct FixedPath __default_path;
static inline void init_default_path() {
    __default_path.len = EXPECT(!= 0, confstr(_CS_PATH, __default_path.bytes, PATH_MAX));
}
const char* get_default_path() {
    ASSERTF(__default_path.bytes[0] != '\0', "");
    return __default_path.bytes;
}

/*******************************************************/

/*
 * Aggregate functions;
 * These functions call the init_* functions above */

static inline void check_function_pointers() {
#ifndef NDEBUG
    /* We use these unwrapped_ function pointers in our code.
     * The rest of the unwrapped_ function pointers are only used if the application (tracee) calls the corresponding libc (without unwrapped_ prefix) function.
     * */
    ASSERTF(unwrapped_close, "");
    ASSERTF(unwrapped_execvpe, "");
    ASSERTF(unwrapped_faccessat, "");
    ASSERTF(unwrapped_fcntl, "");
    ASSERTF(unwrapped_fexecve, "");
    ASSERTF(unwrapped_fork, "");
    ASSERTF(unwrapped_ftruncate, "");
    ASSERTF(unwrapped_mkdirat, "");
    ASSERTF(unwrapped_mmap, "");
    /* TODO: Interpose munmap. See arena.c, ../generator/libc_hooks_source.c */
    /* ASSERTF(unwrapped_munmap, ""); */
    ASSERTF(unwrapped_openat, "");
    ASSERTF(unwrapped_statx, "");

    // assert that function pointers are callable
    struct statx buf;
    EXPECT(== 0, unwrapped_statx(AT_FDCWD, ".", 0, STATX_BASIC_STATS, &buf));
    int fd = EXPECT(> 0, unwrapped_openat(AT_FDCWD, ".", O_PATH));
    EXPECT(== 0, unwrapped_close(fd));
#endif
}

/*
 * After a fork, the process will _appear_ to be initialized, but not be truly initialized.
 * E.g., exec_epoch will be wrong.
 * Therefore, we will reset all the things and call init again.
 */
void init_after_fork() {
    pid_t real_pid = getpid();
    if (UNLIKELY(pid != real_pid)) {
        DEBUG("Re-initializing process");
        // New TID/PID to detect
        tid = tid_initial;
        init_tid();
        pid = real_pid;

        // Fork copies RAM; function pointers should already be initted
        // init_function_pointers();
        check_function_pointers();

        // probe dir hasn't moved, and we already got a copy of it
        // init_probe_dir();

        // But we need to get the _current_ PID process object
        init_process_obj();

        // Default path should already be fine
        //init_default_path();

        /*
         * We don't know if CLONE_FILES was set.
         * We will conservatively assume it is (NOT safe to call arena_destroy)
         * But we assume we have a new memory space, we should clear the mem-mappings.
         * */
        arena_drop_after_fork(&__ops_arena);
        arena_drop_after_fork(&__data_arena);
        init_log_arena();
        init_mut_probe_dir();

        do_init_ops(true);
    }
}

int epoch_inited = 0;
__thread bool thread_inited = false;
pthread_mutex_t epoch_init_lock = PTHREAD_MUTEX_INITIALIZER;

void ensure_initted() {
    bool was_epoch_inited = false;
    if (UNLIKELY(!thread_inited)) {
        init_tid();
        DEBUG("Initializing thread; acquiring mutex");
        // Init TID before trying to init probe_dir
        // Also, it will get included in logs
        EXPECT(== 0, pthread_mutex_lock(&epoch_init_lock));
        if (UNLIKELY(!epoch_inited)) {
            DEBUG("Initializing process");
            was_epoch_inited = true;
            init_pid();               // PID required in probe_dir; also for logs
            init_function_pointers(); // function pointers required in init_probe_dir
            check_function_pointers();
            init_probe_dir();
            init_process_obj();
            init_default_path();
            EXPECT(== 0, pthread_atfork(NULL, NULL, &init_after_fork));
            epoch_inited = true;
        }
        EXPECT(== 0, pthread_mutex_unlock(&epoch_init_lock));
        DEBUG("Released mutex");
        // log arena required in every thread
        // Before do_init_ops
        init_log_arena();
        init_mut_probe_dir();
        thread_inited = true;
        do_init_ops(was_epoch_inited);
    }
}
