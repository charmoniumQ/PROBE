#define _GNU_SOURCE
#ifdef __linux__
#include "linux_defines.h"
#elif defined(__APPLE__)
#include "macos_defines.h"
#endif

#define thrd_current() ((uintptr_t) pthread_self())

#define CLONE_VFORK 0
#define CLONE_THREAD 0
#define CLONE_VM 0
#define CLONE_FILES 0
#define CLONE_FS 0
#define CLONE_IO 0
#define CLONE_PARENT 0
#define CLONE_SIGHAND 0
#define __O_TMPFILE 0
#ifndef AT_EMPTY_PATH
#define AT_EMPTY_PATH 0
#endif

typedef struct dirent dirent64;

#include <assert.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <limits.h>
#include <time.h>
#include <errno.h>
#include <dlfcn.h>
#include <sys/types.h>
#include <dirent.h>
#include <stdarg.h>
#include <sys/resource.h>
#include <pthread.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <utime.h>
#include <unistd.h>
#include <signal.h>
#include <ftw.h>
#include <pthread.h>

/*
 * pycparser cannot parse type-names as function-arguments (as in `va_arg(var_name, type_name)`)
 * so we use some macros instead.
 * To pycparser, these macros are defined as variable names (parsable as arguments).
 * To GCC these macros are defined as type names.
 * */
#define __type_mode_t mode_t
#define __type_charp char*
#define __type_charpp char**

/*
 * Likewise, there is some bug with pycparser unable to parse inline function pointers.
 * So we will use a typedef alias.
 * */
typedef int (*fn_ptr_int_void_ptr)(void*);

static void maybe_init_thread();
static void reinit_process();
static void prov_log_disable();
static int get_exec_epoch_safe();
static bool __process_inited = false;

#define ENV_VAR_PREFIX "PROBE_"

#define PRIVATE_ENV_VAR_PREFIX "__PROBE_"

#include "../generated/libc_hooks.h"

#include "prov_enable.c"

#define ARENA_USE_UNWRAPPED_LIBC
#define ARENA_PERROR
#include "../arena/include/arena.h"

#include "util.c"

/* #include "fd_table.c" */

#include "../include/libprobe/prov_ops.h"

#include "inode_table.c"

#include "global_state.c"

#include "prov_ops.c"

#include "prov_buffer.c"

#include "lookup_on_path.c"

#ifdef __APPLE__
struct __osx_interpose {
    const void* new_func;
    const void* orig_func;
};
#endif

#include "../generated/libc_hooks.c"

static void check_function_pointers() {
    /* We use these unwrapped_ function pointers in our code.
     * The rest of the unwrapped_ function pointers are only used if the application (tracee) calls the corresponding libc (without unwrapped_ prefix) function.
     * */
    assert(unwrapped_faccessat);
    assert(unwrapped_mkdirat);
    assert(unwrapped_openat);
#ifdef __linux__
    assert(unwrapped_statx);
#endif
}

static pthread_mutex_t init_lock = PTHREAD_MUTEX_INITIALIZER;

static void maybe_init_thread() {
    if (unlikely(!__thread_inited)) {
        DEBUG("Acquiring mutex");
        EXPECT(== 0, pthread_mutex_lock(&init_lock));
        DEBUG("Acquired mutex");
        bool was_process_inited = __process_inited;
        prov_log_disable();
        {
            if (unlikely(!__process_inited)) {
                DEBUG("Initializing process");
                init_function_pointers();
                check_function_pointers();
                init_process_global_state();
                __process_inited = true;
            }
            DEBUG("Initializing thread");
            init_thread_global_state();
        }
        EXPECT(== 0, pthread_mutex_unlock(&init_lock));
        prov_log_enable();
        __thread_inited = true;

        if (!was_process_inited) {
            if (get_exec_epoch() == 0) {
                struct Op proc_op = {
                    init_process_op_code,
                    {.init_process = init_current_process()},
                    {0},
                    0,
                    0,
                };
                prov_log_try(proc_op);
                prov_log_record(proc_op);
            }

            struct Op exec_epoch_op = {
                init_exec_epoch_op_code,
                {.init_exec_epoch = init_current_exec_epoch()},
                {0},
                0,
                0,
            };
            prov_log_try(exec_epoch_op);
            prov_log_record(exec_epoch_op);
        }

        struct Op op = {
            init_thread_op_code,
            {.init_thread = init_current_thread()},
            {0},
            0,
            0,
        };
        prov_log_try(op);
        prov_log_record(op);
        prov_log_enable();
    }
}

static void reinit_process() {
    prov_log_disable();
    DEBUG("Re-initializing process");
    /* Function pointers are still fine,
     * since fork() doesn't unload shared libraries. */
    reinit_process_global_state();
    reinit_thread_global_state();
    prov_log_enable();

    struct Op init_process_op = {
        init_process_op_code,
        {.init_process = init_current_process()},
        {0},
        0,
        0,
    };
    prov_log_try(init_process_op);
    prov_log_record(init_process_op);

    struct Op init_exec_op = {
        init_exec_epoch_op_code,
        {.init_exec_epoch = init_current_exec_epoch()},
        {0},
        0,
        0,
    };
    prov_log_try(init_exec_op);
    prov_log_record(init_exec_op);

    struct Op init_thread_op = {
        init_thread_op_code,
        {.init_thread = init_current_thread()},
        {0},
        0,
        0,
    };
    prov_log_try(init_thread_op);
    prov_log_record(init_thread_op);
}
