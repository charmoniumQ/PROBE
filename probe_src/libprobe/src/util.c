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

#define FREE free
/* #define FREE(p) ({ \ */
/*     DEBUG("free: %s: %p", #p, p); \ */
/*     free(p); \ */
/* }) */

#ifndef SOURCE_VERSION
#define SOURCE_VERSION ""
#endif

#define __LOG_PID() fprintf(stderr, "libprobe:pid-%d.%d.%d: ", get_process_id_safe(), get_exec_epoch_safe(), get_sams_thread_id_safe())

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

extern char** environ;

#ifndef NDEBUG
#define printenv() ({ \
    for (char** arg = environ; *arg; ++arg) { \
        DEBUG("printenv: %s", *arg); \
    } \
    NULL; \
})
#else
#define printenv()
#endif

const char* getenv_copy(const char* name) {
    /* Validate input */
    assert(name != NULL);
    assert(strchr(name, '=') == NULL);
    assert(name[0] != '\0');
    assert(environ);
    size_t name_len = strlen(name);
    for (char **ep = environ; *ep != NULL; ++ep) {
        if (unlikely(strncmp(name, *ep, name_len) == 0) && likely((*ep)[name_len] == '=')) {
            return *ep + name_len + 1;
        }
    }
    printenv(); // REMOVE
    return NULL;
}

int setenv_copy(const char* name, const char* value, bool overwrite) {
    /* Validate input */
    assert(name != NULL);
    assert(strchr(name, '=') == NULL);
    assert(name[0] != '\0');
    assert(value != NULL);
    assert(environ);
    size_t name_len = strlen(name);
    size_t value_len = strlen(value);
    char** old_entry = NULL;
    size_t env_count = 0;
    for (char **ep = environ; *ep != NULL; ++ep) {
        env_count++;
        if (unlikely(strncmp(name, *ep, name_len) == 0) && likely((*ep)[name_len] == '=')) {
            old_entry = ep;
        }
    }
    if (old_entry != NULL && overwrite) {
        char* old_value = *old_entry + name_len + 1;
        if (value_len <= strnlen(old_value, value_len + 1)) {
            // New value shorter than or equal to old value
            // Reusing old entry
            memcpy(old_value, value, value_len + 1);
        } else {
            // New value exceeds old value, but we can at least reuse the env vars "slot" in environ
            //free(*old_entry); // TODO: look into if we need to free old_entry
            *old_entry = malloc(name_len + value_len + 2);
            assert(old_entry);
            memcpy(*old_entry, name, name_len);
            (*old_entry)[name_len] = '=';
            memcpy(*old_entry + name_len + 1, value, value_len + 1);
        }
    } else {
        // Adding 2; one for the new env var; one for the trailing sentinel NULL
        char** new_environ = malloc((env_count + 2) * sizeof(char *));
        assert(new_environ);

        // Copy the existing environment variables to the new array
        memcpy(new_environ, environ, env_count * sizeof(char *));

        // Add the new env var
        new_environ[env_count] = malloc(name_len + value_len + 2);
        memcpy(new_environ[env_count], name, name_len);
        new_environ[env_count][name_len] = '=';
        memcpy(new_environ[env_count] + name_len + 1, value, value_len + 1);

        // Add the NULL
        new_environ[env_count + 1] = NULL;

        // TODO: Look into if we need to free the old environ
        environ = new_environ;
    }
    printenv(); // REMOVE
    return 0;
}

/*
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

#ifdef DEBUG_LOG
#define debug_setenv(name, value, overwrite) { \
    char* old_val = (char*) getenv_copy(name); \
    /* we can cast away the const since we do strup later*/  \
    old_val = old_val ? strdup(old_val) : NULL; \
    EXPECT( == 0, setenv_copy(name, value, overwrite)); \
    DEBUG("setenv '%s' = '%s' (formerly '%s'); overwrite? %d", name, value, old_val, overwrite); \
    if (old_val) { free((char*)old_val); } \
}
#else
#define debug_setenv setenv_copy
#endif
