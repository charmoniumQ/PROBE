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

#define likely(x)       __builtin_expect(!!(x), 1)
#define unlikely(x)     __builtin_expect(!!(x), 0)

#ifndef NDEBUG
#define DEBUG_LOG 1
#else
#endif

#define FREE(p) ({free(p); })
/* #define FREE(p) ({ \ */
/*     DEBUG("free: %s: %p", #p, p); \ */
/*     free(p); \ */
/* }) */

#define __LOG(...) ({ \
    fprintf(stderr, __VA_ARGS__); \
})

#define __LOG_SOURCE(msg) ({ \
    __LOG(__FILE__ ":%d:%s(): ", __LINE__, __func__); \
})

#ifdef DEBUG_LOG
#define DEBUG(...) ({ \
    __LOG("libprobe:debug:%d:%d:%d ", get_process_id_safe(), get_exec_epoch_safe(), get_sams_thread_id_safe()); \
    __LOG_SOURCE(); \
    __LOG(__VA_ARGS__); \
    __LOG("\n"); \
})
#else
#define DEBUG(...)
#endif

/* TODO: Replace EXPECT, ASSERTF, NOT_IMPLEMENTED with explicit error handling: { ERR(...); return -1; } */
#ifndef NDEBUG
#define ASSERTF(cond, ...) ({ \
    if (unlikely(!(cond))) { \
        __LOG("    error: "); \
        __LOG_SOURCE(); \
        __LOG("Assertion " #cond " failed: "); \
        __LOG(__VA_ARGS__); \
        __LOG("\n"); \
        abort(); \
    } \
})
#else
#define ASSERTF(...)
#endif

#define NOT_IMPLEMENTED(...) ({ \
    __LOG("    error: "); \
    __LOG_SOURCE(); \
    __LOG("Not implemented: "); \
    __LOG(__VA_ARGS__); \
    __LOG("\n"); \
    abort(); \
})

/* TODO: rewrite this as (const_val, binary_op, expr) */
#ifndef NDEBUG
#define EXPECT(cond, expr) ({ \
    errno = 0; \
    ssize_t ret = (expr); \
    ASSERTF((ret cond), "Expected %s %s, but %s == %ld: %s (%d)", #expr, #cond, #expr, ret, strerror(errno), errno); \
    ret; \
})
#else
#define EXPECT(cond, expr) expr
#endif

#ifndef NDEBUG
#define EXPECT_NONNULL(expr) ({ \
    errno = 0; \
    void* ret = (expr); \
    ASSERTF(ret, "Expected non-null pointer from %s: %s (%d)", #expr, strerror(errno), errno); \
    ret; \
})
#else
#define EXPECT_NONNULL(expr) expr
#endif

#define CHECK_SNPRINTF(s, n, ...) ({ \
    int ret = snprintf(s, n, __VA_ARGS__); \
    ASSERTF(ret > 0, "snprintf returned %d", ret); \
    ASSERTF(ret < n, "%d-long string exceeds destination %d-long destination buffer\n", ret, n); \
    ret; \
})

static OWNED char* path_join(BORROWED char* path_buf, ssize_t left_size, BORROWED const char* left, ssize_t right_size, BORROWED const char* right) {
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
const int unsigned_int_string_size = 12;
/* len(str(2**64)) == 20 */
const int unsigned_long_string_size = 22;
/* len(str(2**63)) + 1 == 20 */
const int signed_long_string_size = 22;
