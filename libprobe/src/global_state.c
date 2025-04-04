#define _GNU_SOURCE

#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <limits.h>

#include "../generated/libc_hooks.h"
#include "util.h"
#include "arena.h"
#include "inode_table.h"
#include "env.h"
#include "prov_buffer.h"
#include "prov_utils.h"

#include "global_state.h"

#define ENV_VAR_PREFIX "PROBE_"

#define PRIVATE_ENV_VAR_PREFIX "__PROBE_"

// getpid/gettid is kind of expensive (40ns per syscall)
// but worth it for debug case

static const pid_t pid_initial = -1;
static pid_t pid = pid_initial;
pid_t get_pid() {
    return EXPECT(== getpid(), pid);
}
static inline void init_pid() {
    pid = EXPECT(!= pid_initial, getpid());
}
pid_t get_pid_safe() {
    if (pid == pid_initial) {
        init_pid();
    }
    return pid;
}

const pid_t tid_initial = -1;
__thread pid_t tid = tid_initial;
pid_t get_tid() {
    return EXPECT(== gettid(), tid);
}
static inline void init_tid() {
    tid = EXPECT(!= tid_initial, gettid());
}
pid_t get_tid_safe() {
    if (tid == tid_initial) {
        init_tid();
    }
    return tid;
}

const int proc_root_initial = -1;
int proc_root = proc_root_initial;
const char* proc_root_env_var = PRIVATE_ENV_VAR_PREFIX "IS_ROOT";
static inline void init_proc_root() {
    ASSERTF(proc_root == proc_root_initial, "%d", proc_root);
    const char* is_root = getenv_copy(proc_root_env_var);
    if (is_root != NULL) {
        ASSERTF(is_root[0] == '0' && is_root[1] == '\0', "'%s'", is_root);
        proc_root = 0;
    } else {
        proc_root = 1;
    }
    DEBUG("Is proc root? %d", proc_root);
}
bool is_proc_root() {
    ASSERTF(proc_root == 1 || proc_root == 0, "%d", proc_root);
    return proc_root;
}

/*
 * exec-family of functions _rep\lace_ pthe process currently being run with a new process, by loading the specified program.
 * It has the same PID, but it is a new process.
 * Therefore, we track the "exec epoch".
 * If this PID is the same as the one in the environment, this must be a new exec epoch of the same.
 * Otherwise, it must be a truly new process.
 */
const int exec_epoch_initial = -1;
int exec_epoch = exec_epoch_initial;
const char* exec_epoch_env_var = PRIVATE_ENV_VAR_PREFIX "EXEC_EPOCH";
const char* pid_env_var = PRIVATE_ENV_VAR_PREFIX "PID";
static inline void init_exec_epoch() {
    ASSERTF(exec_epoch == exec_epoch_initial, "%d", exec_epoch);

    if (!is_proc_root()) {
        const char* last_epoch_pid_str = getenv_copy(pid_env_var);
        ASSERTF(last_epoch_pid_str, "Internal environment variable \"%s\" not set", pid_env_var);

        pid_t last_epoch_pid = EXPECT(> 0, strtoul(last_epoch_pid_str, NULL, 10));

        if (last_epoch_pid == get_pid()) {
            const char* exec_epoch_str = getenv_copy(exec_epoch_env_var);
            ASSERTF(last_epoch_pid_str, "Internal environment variable \"%s\" not set", exec_epoch_env_var);

            size_t last_exec_epoch = EXPECT(>= 0, strtoul(exec_epoch_str, NULL, 10));
            /* Since zero is a sentinel value for strtol,
             * if it returns zero,
             * there's a small chance that exec_epoch_str is an invalid int,
             * We cerify manually */
            ASSERTF(last_exec_epoch != 0 || exec_epoch_str[0] == '0', "%ld", last_exec_epoch);

            exec_epoch = last_exec_epoch + 1;
        } else {
            exec_epoch = 0;
        }
    } else {
        exec_epoch = 0;
    }
    ASSERTF(exec_epoch != exec_epoch_initial, "");

    DEBUG("exec_epoch = %d", exec_epoch);
}
int get_exec_epoch() {
    return EXPECT(!= exec_epoch_initial, exec_epoch);
}
int get_exec_epoch_safe() {
    return exec_epoch;
}

char copy_files = ' ';
const char* copy_files_env_var = PRIVATE_ENV_VAR_PREFIX "COPY_FILES";
struct InodeTable read_inodes;
struct InodeTable copied_or_overwritten_inodes;
static inline void init_copy_files() {
    ASSERTF(copy_files == ' ', "'%c'", copy_files);
    const char* copy_files_str = getenv_copy(copy_files_env_var);
    if (copy_files_str) {
        copy_files = copy_files_str[0];
    } else {
        copy_files = '\0';
    }
    DEBUG("Copy files? %c", copy_files);
    switch (copy_files) {
        case '\0':
            break;
        case 'e': /* eagerly copy files */
        case 'l': /* lazily copy files */
            inode_table_init(&read_inodes);
            inode_table_init(&copied_or_overwritten_inodes);
            break;
        default:
            ERROR("copy_files has invalid value %c", copy_files);
            break;
    }
}
bool should_copy_files_eagerly() {
    ASSERTF(copy_files == '\0' || copy_files == 'e' || copy_files == 'l', "'%c'", copy_files);
    return copy_files == 'e';
}
bool should_copy_files_lazily() {
    ASSERTF(copy_files == '\0' || copy_files == 'e' || copy_files == 'l', "'%c'", copy_files);
    return copy_files == 'l';
}
struct InodeTable* get_read_inodes() {
    ASSERTF(inode_table_is_init(&read_inodes), "");
    return &read_inodes;
}
struct InodeTable* get_copied_or_overwritten_inodes() {
    ASSERTF(inode_table_is_init(&copied_or_overwritten_inodes), "");
    return &copied_or_overwritten_inodes;
}

bool should_copy_files() {
    return should_copy_files_eagerly() || should_copy_files_lazily();
}

#define mkdir_and_descend(my_dirfd, name, child, mkdir, close) ({DEBUG("Calling mkdir_and_descend (%s fd=%d)/%d", dirfd_path(my_dirfd), my_dirfd, child); mkdir_and_descend2(my_dirfd, name, child, mkdir, close); })

static int mkdir_and_descend2(int my_dirfd, const char* name, long child, bool mkdir, bool close) {
    static __thread char buffer[SIGNED_LONG_STRING_SIZE + 1];
    if (!name) {
        CHECK_SNPRINTF(buffer, SIGNED_LONG_STRING_SIZE, "%ld", child);
    }
    if (mkdir) {
        int mkdir_ret = unwrapped_mkdirat(my_dirfd, name ? name : buffer, 0777);
        if (mkdir_ret != 0) {
            int saved_errno = errno;
            list_dir(dirfd_path(my_dirfd), 2);
            ERROR("Cannot mkdir (%s fd=%d)/%ld: %s", dirfd_path(my_dirfd), my_dirfd, child, strerror(saved_errno));
        }
    }
    int sub_dirfd = unwrapped_openat(my_dirfd, name ? name : buffer, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (sub_dirfd == -1) {
        int saved_errno = errno;
#ifndef NDEBUG
        list_dir(dirfd_path(my_dirfd), 2);
#endif
        ERROR(
            "Cannot openat buffer=\"%s\", dirfd=%d, realpath=%s, child=%ld (did we do mkdir? %d), errno=%d,%s",
            name ? name : buffer,
            my_dirfd,
            dirfd_path(my_dirfd),
            child,
            mkdir,
            saved_errno,
            strerror(saved_errno)
        );
    }
    if (close) {
        EXPECT(== 0, unwrapped_close(my_dirfd));
    }
    DEBUG("Returning %s, fd=%d which should be (%s fd=%d)/%s", dirfd_path(sub_dirfd), sub_dirfd, dirfd_path(my_dirfd), my_dirfd, name ? name : buffer);
    return sub_dirfd;
}

const int invalid_dirfd = -1;
int pids_dirfd = invalid_dirfd;
int inodes_dirfd = invalid_dirfd;
const char* probe_dir_env_var = PRIVATE_ENV_VAR_PREFIX "DIR";
char probe_dir[PATH_MAX + 1] = {0};
static inline void init_probe_dir() {
    ASSERTF(pids_dirfd == invalid_dirfd, "%d", pids_dirfd);
    ASSERTF(inodes_dirfd == invalid_dirfd, "%d", inodes_dirfd);
    ASSERTF(probe_dir[0] == '\0', "%s", probe_dir);

    // Get initial probe dir
    const char* probe_dir_env_val = getenv_copy(probe_dir_env_var);

    // Use ERROR instead of EXPECT so this gets caught in optimized-mode as well
    if (!probe_dir_env_val) {
        ERROR("Internal environment variable \"%s\" not set", probe_dir_env_var);
    }
    strncpy(probe_dir, probe_dir_env_val, PATH_MAX);
    if (probe_dir[0] != '/') {
        ERROR("PROBE dir \"%s\" is not absolute", probe_dir);
    }
    if (!is_dir(probe_dir)) {
        ERROR("PROBE dir \"%s\" is not a directory", probe_dir);
    }
    int probe_dirfd = unwrapped_openat(AT_FDCWD, probe_dir, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (probe_dirfd < 0) {
        ERROR("Could not open \"%s\"", probe_dir);
    }
    DEBUG("probe_dir = \"%s\"", probe_dir);

    if (is_proc_root()) {
        int info_dirfd = mkdir_and_descend(probe_dirfd, "info", 0, true, false);
        write_bytes(info_dirfd, "copy_files", should_copy_files() ? "1" : "0", 1);
        EXPECT(== 0, unwrapped_close(info_dirfd));
    }

    pids_dirfd = mkdir_and_descend(probe_dirfd, "pids", 0, is_proc_root(), false);

    ASSERTF(fd_is_valid(pids_dirfd), "");
    ASSERTF(is_dir(dirfd_path(pids_dirfd)), "");

    inodes_dirfd = mkdir_and_descend(probe_dirfd, "inodes", 0, is_proc_root(), false);

    ASSERTF(fd_is_valid(inodes_dirfd), "");
    ASSERTF(is_dir(dirfd_path(inodes_dirfd)), "");

    EXPECT(== 0, unwrapped_close(probe_dirfd));
}

const char* get_probe_dir() {
    ASSERTF(probe_dir[0] != '\0', "probe_dir is empty");
    ASSERTF(is_dir(probe_dir), "'%s' is not dir", probe_dir);
    return probe_dir;
}
int get_inodes_dirfd() {
    ASSERTF(inodes_dirfd != invalid_dirfd, "init_probe_dir() never called");
    ASSERTF(fd_is_valid(inodes_dirfd), "inodes_dirfd inited, but invalid");
    ASSERTF(is_dir(dirfd_path(inodes_dirfd)), "inodes_dirfd inited, but not dir");
    return inodes_dirfd;
}

int epoch_dirfd = invalid_dirfd;
static inline void init_epoch_dir() {
    ASSERTF(epoch_dirfd == invalid_dirfd, "%d", epoch_dirfd);
    ASSERTF(pids_dirfd != invalid_dirfd, "init_probe_dir() never called");
    ASSERTF(fd_is_valid(pids_dirfd), "");
    ASSERTF(is_dir(dirfd_path(pids_dirfd)), "");
    DEBUG("pids_dirfd = %d %s", pids_dirfd, dirfd_path(pids_dirfd));
    DEBUG("Going to \"%s/%d/%d\" (mkdir %d)", probe_dir, get_pid(), get_exec_epoch(), true);
    int pid_dirfd = mkdir_and_descend(pids_dirfd, NULL, get_pid(), get_exec_epoch() == 0, false);
    epoch_dirfd = mkdir_and_descend(pid_dirfd, NULL, get_exec_epoch(), get_tid() == get_pid(), true);
    ASSERTF(epoch_dirfd != invalid_dirfd, "");
}

__thread struct ArenaDir op_arena = { 0 };
__thread struct ArenaDir data_arena = { 0 };
const size_t prov_log_arena_size = 64 * 1024;
static inline void init_log_arena() {
    ASSERTF(!arena_is_initialized(&op_arena), "");
    ASSERTF(!arena_is_initialized(&data_arena), "");
    ASSERTF(epoch_dirfd != invalid_dirfd, "init_epoch_dir() never called");
    ASSERTF(fd_is_valid(epoch_dirfd), "epoch_dirfd inited, but invalid");
    ASSERTF(is_dir(dirfd_path(epoch_dirfd)), "epoch_dirfd inited, but not dir");
    DEBUG("Going to \"%s/%d/%d/%d\" (mkdir %d)", probe_dir, get_pid(), get_exec_epoch(), get_tid(), true);
    int thread_dirfd = mkdir_and_descend(epoch_dirfd, NULL, get_tid(), true, false);
    arena_create(&op_arena, thread_dirfd, "ops", prov_log_arena_size);
    arena_create(&data_arena, thread_dirfd, "data", prov_log_arena_size);
    ASSERTF(arena_is_initialized(&op_arena), "");
    ASSERTF(arena_is_initialized(&data_arena), "");
}
struct ArenaDir* get_op_arena() {
    ASSERTF(arena_is_initialized(&op_arena), "init_log_arena() not called");
    return &op_arena;
}
struct ArenaDir* get_data_arena() {
    ASSERTF(arena_is_initialized(&data_arena), "init_log_arena() not called");
    return &data_arena;
}

char* _DEFAULT_PATH = NULL;
static inline void init_default_path() {
    size_t default_path_size = EXPECT(!= 0, confstr(_CS_PATH, NULL, 0));
    // Technically +1 is not necessary, but it wont' hurt

    _DEFAULT_PATH = EXPECT_NONNULL(malloc(default_path_size + 1));
    EXPECT(!= 0, confstr(_CS_PATH, _DEFAULT_PATH, default_path_size + 1));

    // Technically, this shouldn't be necessary, but it won't hurt.
    _DEFAULT_PATH[default_path_size] = '\0';
}
const char* get_default_path() {
    return EXPECT_NONNULL(_DEFAULT_PATH);
}

/*******************************************************/

/*
 * Aggregate functions;
 * These functions call the init_* functions above */


static inline void check_function_pointers() {
    /* We use these unwrapped_ function pointers in our code.
     * The rest of the unwrapped_ function pointers are only used if the application (tracee) calls the corresponding libc (without unwrapped_ prefix) function.
     * */
    ASSERTF(unwrapped_close, "");
    ASSERTF(unwrapped_execvpe, "");
    ASSERTF(unwrapped_faccessat, "");
    ASSERTF(unwrapped_fexecve, "");
    ASSERTF(unwrapped_fork, "");
    ASSERTF(unwrapped_ftruncate, "");
    ASSERTF(unwrapped_mkdirat, "");
    ASSERTF(unwrapped_openat, "");
    ASSERTF(unwrapped_statx, "");

    // assert that function pointerse are callable
    struct statx buf;
    EXPECT(== 0, unwrapped_statx(AT_FDCWD, ".", 0, STATX_BASIC_STATS, &buf));
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

        // Since we were forked, we can't be the proc root
        proc_root = 0;

        // Since we were forked, we are the 0th exec epoch
        exec_epoch = 0;

        // Fork copies RAM; function pointers should already be initted
        // init_function_pointers();
        check_function_pointers();

        // Fork copies RAM; copy files var should already be initted
        // init_copy_files();

        // Fork copies RAM and fds; probe_dir and fds for probe_dir should be opened already
        // init_probe_dir();

        // But, we will need to open a dir for this epoch, as it is different
        epoch_dirfd = invalid_dirfd;
        init_epoch_dir();

        // Fork copies RAM; default path var should already be initted
        // init_default_path();

        // But we will need to re-open the probe dir, since we are a new process.

        /*
         * We don't know if CLONE_FILES was set.
         * We will conservatively assume it is (NOT safe to call arena_destroy)
         * But we assume we have a new memory space, we should clear the mem-mappings.
         * */
        arena_drop_after_fork(&op_arena);
        arena_drop_after_fork(&data_arena);
        init_log_arena();

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
            init_pid();// PID required in probe_dir; also for logs
            init_proc_root(); // is_proc_root required in init_exec_epoch
            init_exec_epoch(); // init_exec_epoch required in init_probe_dir
            init_function_pointers(); // function pointers required in init_probe_dir
            check_function_pointers();
            init_copy_files();
            init_probe_dir();
            init_epoch_dir();
            init_default_path();
            EXPECT(== 0,
                pthread_atfork(
                    NULL,
                    NULL,
                    &init_after_fork
                )
            );
            epoch_inited = true;
        }
        EXPECT(== 0, pthread_mutex_unlock(&epoch_init_lock));
        DEBUG("Released mutex");
        // log arena required in every thread
        // Before do_init_ops
        init_log_arena();
        thread_inited = true;
        do_init_ops(was_epoch_inited);
    }
}
