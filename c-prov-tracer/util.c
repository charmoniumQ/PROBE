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

#define ASSERTF(cond, ...) \
    if (unlikely(!(cond))) { \
        fprintf(stderr, __FILE__ ":%d:%s: Assertion " #cond " failed: ", __LINE__, __func__); \
        fprintf(stderr, __VA_ARGS__); \
        fprintf(stderr, ", errno = %d %s\n", errno, strerror(errno)); \
        abort(); \
    }

#define NOT_IMPLEMENTED(...) ({ \
    fprintf(stderr, __FILE__ ":%d:%s: Not implemented: ", __LINE__, __func__); \
    fprintf(stderr, __VA_ARGS__); \
    fprintf(stderr, "\n"); \
    abort(); \
})

#define EXPECT(cond, expr) ({\
    errno = 0; \
    ssize_t ret = (expr); \
    ASSERTF((ret cond), "Expected %s %s, but %s == %ld", #expr, #cond, #expr, ret); \
    ret; \
})

#define EXPECT_NONNULL(expr) ({\
    errno = 0; \
    void* ret = (expr); \
    ASSERTF(ret, "Expected non-null pointer from %s", #expr); \
    ret; \
})

#define CHECK_SNPRINTF(s, n, ...) ({\
    int ret = snprintf(s, n, __VA_ARGS__); \
    ASSERTF(ret > 0, "snprintf returned %d", ret); \
    ASSERTF(ret < n, "%d-long string exceeds destination %d-long destination buffer\n", ret, n); \
    ret; \
})

static OWNED char* path_join(BORROWED char* path_buf, ssize_t left_size, BORROWED const char* left, ssize_t right_size, BORROWED const char* right) {
    if (left_size == -1) {
        left_size = strlen(left);
    }
    assert(left[left_size] == '\0');
    if (right_size == -1) {
        right_size = strlen(right);
    }
    assert(right[right_size] == '\0');
    if (!path_buf) {
        path_buf = malloc(left_size + right_size + 2);
    }
    EXPECT_NONNULL(memcpy(path_buf, left, left_size));
    path_buf[left_size] = '/';
    EXPECT_NONNULL(memcpy(path_buf + left_size + 1, right, right_size));
    path_buf[left_size + 1 + right_size] = '\0';
    return path_buf;
}

#define COUNT_NONNULL_VARARGS(first_vararg) \
    ({ \
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
