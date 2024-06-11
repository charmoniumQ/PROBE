#define _GNU_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <limits.h>
#include <time.h>
#include <linux/limits.h>
#include <errno.h>
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
#include <signal.h>
#include <ftw.h>

/*
 * pycparser cannot parse type-names as function-arguments (as in `va_arg(var_name, type_name)`)
 * so we use some macros instead.
 * To pycparser, these macros are defined as variable names (parsable as arguments).
 * To GCC these macros are defined as type names.
 * */
#define __type_mode_t mode_t

/*
 * Likewise, ther is some bug with pycparser unable to parse inline funciton pointers.
 * So we will use a typedef alias.
 * */
typedef int (*fn_ptr_int_void_ptr)(void*);

static void maybe_init_thread();
static void reinit_process();
static void prov_log_disable();
static unsigned int get_process_id_safe();
static unsigned int get_exec_epoch_safe();
static unsigned int get_sams_thread_id_safe();
static bool __process_inited = false;
static __thread bool __thread_inited = false;

#define ENV_VAR_PREFIX "PROBE_"

#define PRIVATE_ENV_VAR_PREFIX "__PROBE_"

#include "../generated/libc_hooks.h"

#include "util.c"

/* #include "fd_table.c" */

#include "../include/prov_ops.h"

#include "global_state.c"

#include "prov_ops.c"

#define USE_UNWRAPPED_LIBC
#include "../../arena/arena.c"

#include "prov_buffer.c"

#include "lookup_on_path.c"

#include "../generated/libc_hooks.c"

/*
 * It seems that sometimes including <sys/stat.h> defines the stat-family of functions as wrappers around __xstat-family of functions.
 * On these systems, stat-family of functions are not found at dynamic-link-or-load-time (not symbols in libc.so.6), since they are defined statically.
 * Since libprobe makes use of unwrapped_ prefixed function pointers to the stat-family, we must have fallbacks in this case.
 * See https://refspecs.linuxfoundation.org/LSB_1.1.0/gLSB/baselib-xstat-1.html
 * https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib---fxstatat-1.html
 * */
static int (*unwrapped___fxstat) (int __ver, int __filedesc, struct stat *__stat_buf);
static int fallback_fstat (int __fd, struct stat *__statbuf) {
    return (*unwrapped___fxstat)(1, __fd, __statbuf);
}
static int (*unwrapped___fxstatat)(int ver, int dirfd, const char * path, struct stat * stat_buf, int flags);
static int fallback_fstatat (int __fd, const char *__filename, struct stat *__statbuf, int __flag) {
    return (*unwrapped___fxstatat)(1, __fd, __filename, __statbuf, __flag);
}

static void check_function_pointers() {
    /* We use these unwrapped_ function pointers in our code.
     * The rest of the unwrapped_ function pointers are only used if the application (tracee) calls the corresponding libc (without unwrapped_ prefix) function.
     * */
    assert(unwrapped_faccessat);
    assert(unwrapped_mkdirat);
    assert(unwrapped_openat);
    if (!unwrapped_fstat) {
      unwrapped___fxstat = dlsym(RTLD_NEXT, "__fxstat");
      if (!unwrapped___fxstat) {
          ERROR("Could not find fstat or __fxstat in your libc");
      }
      unwrapped_fstat = &fallback_fstat;
    }
    if (!unwrapped_fstatat) {
      unwrapped___fxstatat = dlsym(RTLD_NEXT, "__fxstatat");
      if (!unwrapped___fxstatat) {
          ERROR("Could not find fstatat or __fxstatat in your libc");
      }
      unwrapped_fstatat = &fallback_fstatat;
    }
}


static void term_process() {
    DEBUG("term process");
    prov_log_term_process();
}

static void maybe_init_thread() {
    if (unlikely(!__thread_inited)) {
        bool was_process_inited = __process_inited;
        prov_log_disable();
        {
            if (unlikely(!__process_inited)) {
                DEBUG("Initializing process");
                printenv();
                init_function_pointers();
                check_function_pointers();
                init_process_global_state();
                init_process_prov_log();
                atexit(term_process);
                __process_inited = true;
            }
            DEBUG("Initializing thread");
            init_thread_global_state();
            init_thread_prov_log();
        }
        prov_log_enable();
        __thread_inited = true;

        if (!was_process_inited) {
            struct Op op = {
                init_exec_epoch_op_code,
                {.init_exec_epoch = init_current_exec_epoch()},
                {0},
            };
            prov_log_try(op);
            prov_log_record(op);
        }

        struct Op op = {
            init_thread_op_code,
            {.init_thread = init_current_thread()},
            {0},
        };
        prov_log_try(op);
        prov_log_record(op);
        prov_log_enable();
    }
}

static void reinit_process() {
    prov_log_disable();
    DEBUG("Re-initializing process");
    printenv();
    /* Function pointers are still fine,
     * since fork() doesn't unload shared libraries. */
    reinit_process_global_state();
    reinit_process_prov_log();
    atexit(term_process);
    DEBUG("Re-initializing thread");
    reinit_thread_global_state();
    reinit_thread_prov_log();
    struct Op init_exec_op = {
        init_exec_epoch_op_code,
        {.init_exec_epoch = init_current_exec_epoch()},
        {0},
    };
    prov_log_try(init_exec_op);
    prov_log_record(init_exec_op);
    struct Op init_thread_op = {
        init_thread_op_code,
        {.init_thread = init_current_thread()},
        {0},
    };
    prov_log_try(init_thread_op);
    prov_log_record(init_thread_op);
    prov_log_enable();
}
