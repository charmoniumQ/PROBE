#pragma once
#define _GNU_SOURCE          /* See feature_test_macros(7) */
#include <stdio.h>
#include <limits.h>
#include <stdlib.h>  
#include <string.h>  
#include <unistd.h> 
#include <sys/types.h> 
#include <sys/syscall.h> 
#include <sys/stat.h>
#include <limits.h>
#include <limits.h>
#include <fcntl.h>
#include <stdbool.h>
#include <assert.h> 
#include <errno.h>
#include <ftw.h>
#include <dirent.h>
#include "declarations.h"
#include "../generated/libc_hooks.h"

/*
 * OWNED/BORROWED determins who is responsible for freeing a pointer received or returned by a function-call.
 * Obviously, this is inspired by Rust.
 * C compiler can't check this at compile-time, but these macros serve to document the function-signatures for humans.
 * E.g.,
 *
 *     OWNED int* copy_int(BORROWED int*)
 *
 * If a function-call returns an OWNED pointer, the callee has to free it.
 * If a function-call receives an OWNED pointer, the callee can't use it after the call.
 * If a function-call returns a BORROWED pointer, the callee can't free it.
 * If a function-call receives a BORROWED pointer, the function can't free it.
 * */
#include <sys/sendfile.h>
#define OWNED
#define BORROWED

#define likely(x)       __builtin_expect(!!(x), 1)
#define unlikely(x)     __builtin_expect(!!(x), 0)

#ifndef NDEBUG
#define DEBUG_LOG 1
#else
#endif

#define FREE free
/* #define FREE(p) ({ \ */
/*     DEBUG("free: %s: %p", #p, p); \ */
/*     free(p); \ */
/* }) */

#ifndef SOURCE_VERSION
#define SOURCE_VERSION ""
#endif

static pid_t my_gettid(){
    return (pid_t)syscall(SYS_gettid);
}

#define __LOG_PID() fprintf(stderr, "libprobe:pid-%d.%d.%d: ", getpid(), get_exec_epoch_safe(), my_gettid())

#define __LOG_SOURCE() fprintf(stderr, SOURCE_VERSION ":" __FILE__ ":%d:%s(): ", __LINE__, __func__)

#ifdef DEBUG_LOG
#define DEBUG(...) ({ \
    __LOG_PID(); \
    __LOG_SOURCE(); \
    fprintf(stderr, __VA_ARGS__); \
    fprintf(stderr, "\n"); \
})
#else
#define DEBUG(...)
#endif

/* TODO: Replace EXPECT, ASSERTF, NOT_IMPLEMENTED with explicit error handling: { ERR(...); return -1; } */
#ifndef NDEBUG
#define ASSERTF(cond, ...) ({ \
    if (unlikely(!(cond))) { \
        __LOG_PID(); \
        __LOG_SOURCE(); \
        fprintf(stderr, "Assertion " #cond " failed: "); \
        fprintf(stderr, __VA_ARGS__); \
        fprintf(stderr, "\n"); \
	    prov_log_disable(); \
        exit(1); \
    } \
})
/* TODO: rewrite this as (const_val, binary_op, expr) */
#define EXPECT(cond, expr) ({ \
    errno = 0; \
    ssize_t ret = (expr); \
    ASSERTF((ret cond), "Expected %s %s, but %s == %ld: %s (%d)", #expr, #cond, #expr, ret, strerror(errno), errno); \
    ret; \
})
#define EXPECT_NONNULL(expr) ({ \
    errno = 0; \
    void* ret = (expr); \
    ASSERTF(ret, "Expected non-null pointer from %s: %s (%d)", #expr, strerror(errno), errno); \
    ret; \
})
#else
#define ASSERTF(...)
#define EXPECT(cond, expr) expr
#define EXPECT_NONNULL(expr) expr
#endif

#define NOT_IMPLEMENTED(...) ({ \
    __LOG_PID(); \
    __LOG_SOURCE(); \
    fprintf(stderr, "Not implemented: "); \
    fprintf(stderr, __VA_ARGS__); \
    fprintf(stderr, "\n"); \
    prov_log_disable(); \
    exit(1); \
})

#define ERROR(...) ({ \
    __LOG_PID(); \
    __LOG_SOURCE(); \
    fprintf(stderr, __VA_ARGS__); \
    fprintf(stderr, "\n"); \
    prov_log_disable(); \
    exit(1); \
})

#define CHECK_SNPRINTF(s, n, ...) ({ \
    int ret = snprintf(s, n, __VA_ARGS__); \
    ASSERTF(ret > 0, "snprintf returned %d", ret); \
    ASSERTF(ret < n, "%d-long string exceeds destination %lu-long destination buffer\n", ret, n); \
    ret; \
})

static OWNED char* path_join(BORROWED char* path_buf, size_t left_size, BORROWED const char* left, size_t right_size, BORROWED const char* right) {
    if (left_size == -1) {
        left_size = strlen(left);
    }
    if (right_size == -1) {
        right_size = strlen(right);
    }
    if (!path_buf) {
        path_buf = malloc(left_size + right_size + 2);
    }
    EXPECT_NONNULL(memcpy(path_buf, left, left_size));
    path_buf[left_size] = '/';
    EXPECT_NONNULL(memcpy(path_buf + left_size + 1, right, right_size));
    path_buf[left_size + 1 + right_size] = '\0';
    return path_buf;
}

#define COUNT_NONNULL_VARARGS(first_vararg) ({ \
    va_list vl; \
    va_start(vl, first_vararg); \
    size_t n_varargs = 0; \
    while (va_arg(vl, char*)) { \
        ++n_varargs; \
    } \
    va_end(vl); \
    n_varargs; \
})

/* len(str(2**32)) == 10. Let's add 1 for a null byte and 1 just for luck :) */
#define unsigned_int_string_size (12)
/* len(str(2**64)) == 20 */
#define unsigned_long_string_size (22)
/* len(str(2**63)) + 1 == 20 */
#define signed_long_string_size (22)

extern char** environ;

#ifndef NDEBUG
#define printenv() ({ \
    for (char** arg = environ; *arg; ++arg) { \
        DEBUG("printenv: %s", *arg); \
    } \
    ((void)0); \
})
#else
#define printenv() ((void)0)
#endif

static const char* getenv_copy(const char* name) {
    /* Validate input */
    assert(name);
    assert(strchr(name, '=') == NULL);
    assert(name[0]);
    assert(environ);
    size_t name_len = strlen(name);
    for (char **ep = environ; *ep; ++ep) {
        if (unlikely(strncmp(name, *ep, name_len) == 0) && likely((*ep)[name_len] == '=')) {
            return *ep + name_len + 1;
        }
    }
    return NULL;
}

/*
 * TODO: Test this
 *
 * Somehow, calling glibc's getenv here doesn't work (???) for the case `bash -c 'bash -c echo'` with libprobe.
 * In that case, the following code trips up:
 *
 *     debug_getenv(__PROBE_PROCESS_BIRTH_TIME); // prints getenv: __PROBE_PROESS_BIRTH_TIME = 1000.2000 or something
 *     debug_setenv(__PROBE_PROCESS_TRACEE_PID); // prints setenv: __PROBE_PROCESS_TRACEE_PID = 2002 (formerly 2001) or something
 *     dcebug_getenv(__PROBE_PROCESS_BIRTH_TIME); // prints getenv: __PROBE_PROESS_BIRTH_TIME = (null)
 *
 * I'm not sure how the intervening setenv of TRACEE PID is affecting the value of BIRTH TIME.
 *
 * Somehow, when I re-implemented getenv/setenv here, the bug is absent. Wtf?
 * At least this works.
 *
 * I think it has something to do with libc's assumptions about library loading
 *
 */
#ifdef DEBUG_LOG
#define debug_getenv(name) ({ \
    const char* ret = getenv_copy(name); \
    DEBUG("getenv '%s' = '%s'", name, ret); \
    ret; \
})
#else
#define debug_getenv getenv_copy
#endif

static bool is_dir(const char* dir) {
    struct statx statx_buf;
    int statx_ret = unwrapped_statx(AT_FDCWD, dir, 0, STATX_TYPE, &statx_buf);
    if (statx_ret != 0) {
        return false;
    } else {
        return (statx_buf.stx_mode & S_IFMT) == S_IFDIR;
    }
}

static OWNED const char* dirfd_path(int dirfd) {
    static char dirfd_proc_path[PATH_MAX];
    CHECK_SNPRINTF(dirfd_proc_path, (unsigned long) PATH_MAX, "/proc/self/fd/%d", dirfd);
    char* resolved_buffer = malloc(PATH_MAX);
    const char* ret = unwrapped_realpath(dirfd_proc_path, resolved_buffer);
    return ret;
}

/*
 * dirfd(3) is not tolerant of NULL:
 * header: https://github.com/bminor/glibc/blob/9fc639f654dc004736836613be703e6bed0c36a8/dirent/dirent.h#L226
 * src: https://github.com/bminor/glibc/blob/9fc639f654dc004736836613be703e6bed0c36a8/sysdeps/unix/sysv/linux/dirfd.c#L27
 *
 * -1 is never a valid fd because it's the error value for syscalls that return fds, so we can do the same.
 */
static int try_dirfd(BORROWED DIR* dirp) {
    return dirp ? (dirfd(dirp)) : (-1);
}

#ifndef NDEBUG
static int fd_is_valid(int fd) {
    return unwrapped_fcntl(fd, F_GETFD) != -1 || errno != EBADF;
}

static void listdir(const char* name, int indent) {
    // https://stackoverflow.com/a/8438663
    DIR *dir = NULL;
    struct dirent *entry = NULL;

    if (!(dir = unwrapped_opendir(name)))
        return;

    while ((entry = unwrapped_readdir(dir))) {
        if (entry->d_type == DT_DIR) {
            char path[PATH_MAX];
            if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
                continue;
            snprintf(path, sizeof(path), "%s/%s", name, entry->d_name);
            DEBUG("%*s%s/", indent, "", entry->d_name);
            listdir(path, indent + 2);
        } else {
            DEBUG("%*s%s", indent, "", entry->d_name);
        }
    }
    unwrapped_closedir(dir);
}

#endif

/* strtol in libc is not totally static;
 * It is defined itself as a static function, but that static code calls some dynamically loaded function.
 * This would be fine, except some older versions of glibc may not have the deynamic function. */
static unsigned long my_strtoul(const char *restrict string, char **restrict string_end, int base) {
    unsigned long accumulator = 0;
    const char* ptr = string;
    while (*ptr != '\0') {
        int value = 0;
        if ('0' <= *ptr && *ptr <= '9') {
            value = *ptr - '0';
        } else if ('A' <= *ptr && *ptr < 'A' + base) {
            value = *ptr - 'A' + 10;
        } else if ('a' <= *ptr && *ptr < 'a' + base) {
            value = *ptr - 'a' + 10;
        } else {
            return 0;
        }
        accumulator = accumulator * base + value;
        ptr++;
    }
    if (string_end) {
        *string_end = (char*) ptr;
    }
    return accumulator;
}

/* Copy char* const argv[] into the arena.
 * If argc argument is 0, compute argc and store there (if the size actually was zero, this is no bug).
 * If argc argument is positive, assume that is the argc.
 * */
static char* const* arena_copy_argv(struct ArenaDir* arena_dir, char * const * argv, size_t* argc) {
    if (*argc == 0) {
        /* Compute argc and store in *argc */
        for (char * const* argv_p = argv; *argv_p; ++argv_p) {
            (*argc)++;
        }
    }

    char** argv_copy = arena_calloc(arena_dir, *argc + 1, sizeof(char*));

    for (size_t i = 0; i < *argc; ++i) {
        size_t length = strlen(argv[i]);
        argv_copy[i] = arena_calloc(arena_dir, length + 1, sizeof(char));
        memcpy(argv_copy[i], argv[i], length + 1);
        assert(!argv_copy[i][length]);
    }

    assert(!argv[*argc]);
    argv_copy[*argc] = NULL;

    return argv_copy;
}

int copy_file(int src_dirfd, const char* src_path, int dst_dirfd, const char* dst_path, ssize_t size) {
    /*
    ** Adapted from:
    ** https://stackoverflow.com/a/2180157
     */
    int src_fd = unwrapped_openat(src_dirfd, src_path, O_RDONLY);
    int dst_fd = unwrapped_openat(dst_dirfd, dst_path, O_WRONLY | O_CREAT, 0666);
    int result = 0;
    off_t copied = 0;
    while (result == 0 && copied < size) {
        ssize_t written = sendfile(dst_fd, src_fd, &copied, SSIZE_MAX);
        copied += written;
        if (written == -1) {
            result = -1;
        }
    }

    unwrapped_close(src_fd);
    unwrapped_close(dst_fd);

    return result;
}

int write_bytes(int dirfd, const char* path, const char* content, ssize_t size) {
    int fd = unwrapped_openat(dirfd, path, O_RDWR | O_CREAT, 0666);
    assert(fd > 0);
    ssize_t ret = write(fd, content, size);
    assert(ret == size);
    EXPECT( == 0, unwrapped_close(fd));
    return ret == size;
}
