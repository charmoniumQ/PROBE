#define _GNU_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
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

/*
 * I can't include unistd.h because it also defines dup3.
  */
ssize_t write(int fd, const char* buf, size_t count);
long syscall(long number, ...);
pid_t getpid(void);
struct utimbuf;
char *getcwd(char *buf, size_t size);
struct statx; /* TODO: old glibc's don't have statx. How to deal? */
#define STDIN_FILENO 0
#define STDOUT_FILENO 1
#define STDERR_FILENO 2

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

void construct_libprov_thread();

static char* const __prov_log_verbose_envvar = "PROV_LOG_VERBOSE";
static int __prov_log_verbose = -1;
/* -1 means unknown; 0 means known false; 1 means known true  */
static int prov_log_verbose() {
    if (__prov_log_verbose == -1) {
        char* __prov_log_verbose_envval = getenv(__prov_log_verbose_envvar);
        if (__prov_log_verbose_envval && __prov_log_verbose_envval[0] != '\0') {
            __prov_log_verbose = 1;
        } else {
            __prov_log_verbose = 0;
        }
    }
    return __prov_log_verbose;
}

#include "libc_hooks.h"

#include "util.c"

#include "inode_triple.c"

#include "fd_table.c"

#include "prov_operations.c"

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

__attribute__ ((constructor)) void construct_libprov() {
    setup_function_pointers();
    /* We use these o_ function pointers in our code.
     * The rest of the o_ function pointers are only used if the application (tracee) calls the corresponding libc (without o_ prefix) function.
     * */
    assert(o_access);
    assert(o_mkdir);
    assert(o_fopen); /* TODO: replace fopen/fclose with openat/close */
    assert(o_openat);
    assert(o_fclose);
    if (!o_fstat) {
      EXPECT(, o___fxstat = dlsym(RTLD_NEXT, "__fxstat"));
      o_fstat = &fallback_fstat;
    }
    if (!o_fstatat) {
      EXPECT(, o___fxstatat = dlsym(RTLD_NEXT, "__fxstatat"));
      o_fstatat = &fallback_fstatat;
    }
}

__attribute__ ((destructor)) void destruct_libprov() {
    prov_log_save();
}
