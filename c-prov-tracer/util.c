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

#define EXPECT(cond, expr) ({\
    errno = 0; \
    size_t ret = (size_t) (expr); \
    if (unlikely(!(ret cond))) { \
        fprintf(stderr, "failure on %s:%d: %s: assertion !(ret %s) failed for ret=%ld; errno=%d, strerror(errno)=\"%s\"\n", __FILE__, __LINE__, #expr, #cond, ret, errno, strerror(errno)); \
        abort(); \
    } \
    ret; \
})

#define CHECK_SNPRINTF(s, n, ...) ({\
        int ret = snprintf(s, n, __VA_ARGS__); \
        if (unlikely(ret < 0)) { \
            fprintf(stderr, "failure on %s:%d: snprintf: %s\n", __FILE__, __LINE__, strerror(errno)); \
            abort(); \
        } \
        if (unlikely(n <= ret)) { \
            fprintf(stderr, "failure on %s:%d: snprintf: %d-long string exceeds destination %d-long destination buffer\n", __FILE__, __LINE__, ret, n); \
            abort(); } \
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
    EXPECT(, memcpy(path_buf, left, left_size));
    path_buf[left_size] = '/';
    EXPECT(, memcpy(path_buf + left_size + 1, right, right_size));
    path_buf[left_size + 1 + right_size] = '\0';
    return path_buf;
}
