#pragma once

#define _GNU_SOURCE

// https://stackoverflow.com/a/78062291/1078199
#include <stdarg.h>    // for va_arg, va_end, va_start, va_list
#include <stdbool.h>   // for bool
#include <stdio.h>     // for snprintf, size_t
#include <sys/types.h> // for ssize_t

#include "debug_logging.h" // for ASSERTF

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
#define OWNED
#define BORROWED

#define LIKELY(x) __builtin_expect(!!(x), 1)
#define UNLIKELY(x) __builtin_expect(!!(x), 0)

#define CHECK_SNPRINTF(s, n, ...)                                                                  \
    ({                                                                                             \
        int ret = snprintf(s, n, __VA_ARGS__);                                                     \
        ASSERTF(ret > 0, "snprintf returned %d", ret);                                             \
        ASSERTF(ret < n, "%d-long string exceeds destination %d-long destination buffer\n", ret,   \
                n);                                                                                \
        ret;                                                                                       \
    })

#define COUNT_NONNULL_VARARGS(first_vararg)                                                        \
    ({                                                                                             \
        va_list vl;                                                                                \
        va_start(vl, first_vararg);                                                                \
        size_t n_varargs = 0;                                                                      \
        while (va_arg(vl, char*)) {                                                                \
            ++n_varargs;                                                                           \
        }                                                                                          \
        va_end(vl);                                                                                \
        n_varargs;                                                                                 \
    })

/* len(str(2**32)) == 10. Let's add 1 for a null byte and 1 just for luck :) */
#define UNSIGNED_INT_STRING_SIZE (12)
/* len(str(2**64)) == 20 */
#define UNSIGNED_LONG_STRING_SIZE (22)
/* len(str(2**63)) + 1 == 20 */
#define SIGNED_LONG_STRING_SIZE (22)

#define MAX(a, b) ((a) < (b) ? (b) : (a))

__attribute__((visibility("hidden"))) bool is_dir(const char* dir) __attribute__((nonnull));

__attribute__((visibility("hidden"))) OWNED const char* dirfd_path(int dirfd)
    __attribute__((returns_nonnull));

__attribute__((visibility("hidden"))) OWNED char*
path_join(BORROWED char* path_buf, ssize_t left_size, BORROWED const char* left, ssize_t right_size,
          BORROWED const char* right) __attribute__((nonnull(3, 5), returns_nonnull));

__attribute__((visibility("hidden"))) int fd_is_valid(int fd);

__attribute__((visibility("hidden"))) void list_dir(const char* name, int indent)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) int copy_file(int src_dirfd, const char* src_path,
                                                    int dst_dirfd, const char* dst_path,
                                                    ssize_t size) __attribute__((nonnull));

__attribute__((visibility("hidden"))) void write_bytes(int dirfd, const char* path,
                                                       const char* content, ssize_t size)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) unsigned char ceil_log2(unsigned int val)
    __attribute__((pure));

__attribute__((visibility("hidden"))) char* const* read_null_delim_file(const char* path,
                                                                        size_t* array_len)
    __attribute__((nonnull, returns_nonnull, malloc));

__attribute__((unused)) static inline void __mark_as_used__util_h(int f, ...) {
    char buf[10];
    CHECK_SNPRINTF(buf, 10, "");
    COUNT_NONNULL_VARARGS(f);
    __attribute__((unused)) bool a = true;
    __attribute__((unused)) size_t b = 1;
}

__attribute__((visibility("hidden"))) unsigned int my_atoui(const char* s) __attribute__((nonnull));
