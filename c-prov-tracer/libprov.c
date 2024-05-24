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
#include <utime.h>
#include <unistd.h>
#include <signal.h>

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
static void term_process();
static bool prov_log_verbose();

#define ENV_VAR_PREFIX "PROV_LOG_"

#define PRIVATE_ENV_VAR_PREFIX "__PROV_LOG_"

#include "libc_hooks.h"

#include "util.c"

/* #include "fd_table.c" */

#include "prov_ops.h"

#include "global_state.c"

#include "prov_ops.c"

#include "prov_buffer.c"

#include "lookup_on_path.c"

#include "libc_hooks.c"

/*
 * It seems that sometimes including <sys/stat.h> defines the stat-family of functions as wrappers around __xstat-family of functions.
 * On these systems, stat-family of functions are not found at dynamic-link-or-load-time (not symbols in libc.so.6), since they are defined statically.
 * Since libprov makes use of o_ prefixed function pointers to the stat-family, we must have fallbacks in this case.
 * See https://refspecs.linuxfoundation.org/LSB_1.1.0/gLSB/baselib-xstat-1.html
 * https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib---fxstatat-1.html
 * */
static int (*o___fxstat) (int __ver, int __filedesc, struct stat *__stat_buf);
static int fallback_fstat (int __fd, struct stat *__statbuf) {
    return (*o___fxstat)(1, __fd, __statbuf);
}
static int (*o___fxstatat)(int ver, int dirfd, const char * path, struct stat * stat_buf, int flags);
static int fallback_fstatat (int __fd, const char *__filename, struct stat *__statbuf, int __flag) {
    return (*o___fxstatat)(1, __fd, __filename, __statbuf, __flag);
}

static void check_function_pointers() {
    /* We use these o_ function pointers in our code.
     * The rest of the o_ function pointers are only used if the application (tracee) calls the corresponding libc (without o_ prefix) function.
     * */
    assert(o_access); /* TODO: replace with faccessat */
    assert(o_mkdir); /* TODO: replace with mkdirat */
    assert(o_openat);
    if (!o_fstat) {
      o___fxstat = EXPECT_NONNULL(dlsym(RTLD_NEXT, "__fxstat"));
      o_fstat = &fallback_fstat;
    }
    if (!o_fstatat) {
      o___fxstatat = EXPECT_NONNULL(dlsym(RTLD_NEXT, "__fxstatat"));
      o_fstatat = &fallback_fstatat;
    }
}

static bool __process_inited = false;
static __thread bool __thread_inited = false;
static void maybe_init_thread() {
    if (unlikely(!__thread_inited)) {
        bool was_process_inited = __process_inited;
        prov_log_disable();
        {
            if (unlikely(!__process_inited)) {
                prov_log_disable();
                init_function_pointers();
                check_function_pointers();
                init_process_global_state();
                DEBUG("Initializing process %d", get_process_id());
                init_process_prov_log();
                atexit(term_process);
                __process_inited = true;
            }
            init_thread_global_state();
            DEBUG("Initializing thread %d of process %d", get_sams_thread_id(), get_process_id());
            init_thread_prov_log();
        }
        prov_log_enable();
        __thread_inited = true;

        if (!was_process_inited) {
            struct Op op = {
                init_process_op_code,
                {.init_process = init_current_process()},
            };
            prov_log_try(op);
            prov_log_record(op);
        }

        struct Op op = {
            init_thread_op_code,
            {.init_thread = init_current_thread()},
        };
        prov_log_try(op);
        prov_log_record(op);
        prov_log_enable();
    }
}

static void term_process() {
    DEBUG("cleanup started %d %d", get_process_id(), get_sams_thread_id());
    prov_log_disable();
    prov_log_term_process();
    DEBUG("cleanup done %d %d", get_process_id(), get_sams_thread_id());
}
