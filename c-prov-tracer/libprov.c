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
#include <ftw.h>
#include <stdarg.h>
#include <sys/resource.h>
#include <pthread.h>
#include <malloc.h>
#include <sys/sysmacros.h>

/*
 * I can't include unistd.h because it also defines dup3.
 */
pid_t getpid(void);
pid_t gettid(void);
struct utimbuf;
char *getcwd(char *buf, size_t size);

/*
 * pycparser cannot parse type-names as function-arguments (as in `va_arg(var_name, type_name)`)
 * so we use some macros instead.
 * To pycparser, these macros are defined as variable names (parsable as arguments).
 * To GCC these macros are defined as type names.
 * */
#define __type_mode_t mode_t

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

__attribute__ ((constructor)) void construct_libprov() {
    setup_function_pointers();
}

__attribute__ ((destructor)) void destruct_libprov() {
    prov_log_save();
}
