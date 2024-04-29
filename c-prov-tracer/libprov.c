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

#include "libc_hooks.h"

#include "util.c"

#include "fd_table.c"

#include "path_lib.c"

#include "prov_operations.c"

#include "prov_buffer.c"

#include "libc_hooks.c"

__attribute__ ((constructor)) void setup_libprov() {
    setup_function_pointers();
}
