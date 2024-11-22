
#ifndef MAC_DEFINES_H
#define MAC_DEFINES_H

#ifdef __APPLE__

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
#include <sys/stat.h>
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
#define thrd_success 0
#define thrd_nomem 1

#define ftruncate64 ftruncate
#define truncate64 truncate
#define unwrapped_open64 unwrapped_open
#define unwrapped_openat64 unwrapped_openat
#define THREAD_LOCAL _Thread_local

static pid_t (*unwrapped__Fork)(void);

typedef int (*thrd_start_t)(void *);
typedef off_t off64_t;
typedef struct stat stat64_t;
typedef struct stat stat64;

typedef pthread_t thrd_t;
typedef struct {
    thrd_start_t func;
    void *arg;
} thrd_wrapper_args_t;

typedef int (*__ftw64_func_t)(const char *, const struct stat64 *, int);
typedef int (*__nftw64_func_t)(const char *, const struct stat64 *, int, struct FTW *);
typedef int (*__ftw_func_t)(const char *fpath, const struct stat *sb, int typeflag);
typedef int (*__nftw_func_t)(const char *fpath, const struct stat *sb, int typeflag, struct FTW *ftwbuf);

void *thrd_start_wrapper(void *arg) {
    thrd_wrapper_args_t *wrapper_args = (thrd_wrapper_args_t *)arg;
    int res = wrapper_args->func(wrapper_args->arg);
    free(wrapper_args);
    return (void *)(intptr_t)res;
}

static int unwrapped_thrd_create(thrd_t *thr, thrd_start_t func, void *arg) {
    thrd_wrapper_args_t *wrapper_args = malloc(sizeof(thrd_wrapper_args_t));
    if (wrapper_args == NULL) {
        return thrd_nomem;
    }
    wrapper_args->func = func;
    wrapper_args->arg = arg;
    int ret = pthread_create(thr, NULL, thrd_start_wrapper, wrapper_args);
    if (ret != 0) {
        free(wrapper_args);
    }
    return (ret == 0) ? thrd_success : ret;
}

static pid_t unwrapped_clone(int (*fn)(void *), void *child_stack, int flags, void *arg, ...) {
    errno = ENOSYS;
    return -1;
}

static inline int fstatat64(int dirfd, const char *pathname, struct stat64 *buf, int flags) {
    return fstatat(dirfd, pathname, (struct stat *)buf, flags);
}
static _Thread_local bool __thread_inited = false;

#endif
#define thrd_current() ((uintptr_t) pthread_self())

#endif
