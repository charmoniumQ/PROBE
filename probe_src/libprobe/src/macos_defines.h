#pragma once

extern char** environ;
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
#define thrd_success 0
#define thrd_nomem 1
#define ftruncate64 ftruncate
#define truncate64 truncate

typedef off_t off64_t;
typedef int (*__ftw64_func_t)(const char *, const struct stat64 *, int);
typedef int (*__nftw64_func_t)(const char *, const struct stat64 *, int, struct FTW *);
typedef int (*__ftw_func_t)(const char *fpath, const struct stat *sb, int typeflag);
typedef int (*__nftw_func_t)(const char *fpath, const struct stat *sb, int typeflag, struct FTW *ftwbuf);
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

static bool __thread_inited = false;

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
