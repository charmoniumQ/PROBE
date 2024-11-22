#pragma once

#include <limits.h>
#include <malloc/malloc.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>
#include <sys/types.h>
#include <stdint.h>
#include <sys/param.h>
#include <stdlib.h>
#include <pthread.h>
#include <errno.h>
#include <stdbool.h>
#include <ftw.h>


#define F_SETSIG 0
#define F_SETLEASE 0
#define F_NOTIFY 0
#define F_SETPIPE_SZ 0
#define F_ADD_SEALS 0
#define F_GETOWN_EX 0
#define F_SETOWN_EX 0
#define F_GET_RW_HINT 0
#define F_SET_RW_HINT 0
#define F_GET_FILE_RW_HINT 0
#define F_SET_FILE_RW_HINT 0

typedef int (*thrd_start_t)(void *);

typedef pthread_t thrd_t;
typedef struct {
    thrd_start_t func;
    void *arg;
} thrd_wrapper_args_t;

void *thrd_start_wrapper(void *arg) {
    thrd_wrapper_args_t *wrapper_args = (thrd_wrapper_args_t *)arg;
    int res = wrapper_args->func(wrapper_args->arg);
    free(wrapper_args);
    return (void *)(intptr_t)res;
}

static __thread bool __thread_inited = false;

#define thrd_current() ((uintptr_t) pthread_self())

int platform_independent_execvpe(const char *program, char **argv, char **envp) {
    /*
    ** https://stackoverflow.com/a/7789795/1078199
     */
    char **saved = environ;
    int rc;
    environ = envp;
    rc = execvp(program, argv);
    environ = saved;
    return rc;
}
