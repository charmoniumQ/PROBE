#define _GNU_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <stdbool.h>
#include <limits.h>
#include <linux/limits.h>
#include <dlfcn.h>
#include <sys/types.h>
#include <dirent.h>
#include <stdarg.h>
#include <sys/resource.h>
#include <pthread.h>
#include <malloc.h>
#include <sys/sysmacros.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <utime.h>
#include <unistd.h>
#include <ftw.h>
#include <threads.h>
#include <pthread.h>

static bool __process_inited = false;
static __thread bool __thread_inited = false;

#include "../generated/libc_hooks.h"

#include "declarations.h"

#include "util.h"

#include "../include/libprobe/prov_ops.h"

#include "global_state.c"

#include "prov_ops.c"

#include "prov_buffer.c"

#include "lookup_on_path.c"

#include "../generated/libc_hooks.c"

static void check_function_pointers() {
    /* We use these unwrapped_ function pointers in our code.
     * The rest of the unwrapped_ function pointers are only used if the application (tracee) calls the corresponding libc (without unwrapped_ prefix) function.
     * */
    assert(unwrapped_faccessat);
    assert(unwrapped_mkdirat);
    assert(unwrapped_openat);
    assert(unwrapped_statx);
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
