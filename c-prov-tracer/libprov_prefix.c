#define _GNU_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <errno.h>
#include <linux/limits.h>
#include <errno.h>
#include <dlfcn.h>
#include <sys/types.h>
#include <dirent.h>
#include <ftw.h>
#include <sys/resource.h>

/*
 * I can't include unistd.h because it also defines dup3.
 */
pid_t getpid(void);
pid_t gettid(void);

#define EXPECT(cond, expr) ({\
    int ret = expr; \
    if (!(ret cond)) { \
        fprintf(stderr, "failure on %s:%d: %s: !(%d %s)\nstrerror: %s\n", __FILE__, __LINE__, #expr, ret, #cond, strerror(errno)); \
        abort(); \
    } \
    ret; \
})

static __thread FILE* log = NULL;
static __thread bool disable_log = false;

static FILE* get_prov_log_file(void);

static void save_prov_log(void);

/* static char getname_buffer[PATH_MAX]; */
/* static char* getname(const FILE* file); */
