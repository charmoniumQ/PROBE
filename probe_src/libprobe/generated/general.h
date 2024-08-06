#pragma once 

#include <string.h>
#include <sys/types.h>
#include <stdlib.h> 
#define OWNED
#define BORROWED

#define likely(x)       __builtin_expect(!!(x), 1)
#define unlikely(x)     __builtin_expect(!!(x), 0)

#ifndef NDEBUG
#define DEBUG_LOG 1
#else
#endif

typedef int (*fn_ptr_int_void_ptr)(void*);
typedef void* idtype_t;
typedef void* siginfo_t;
typedef void* thrd_t;
typedef void* thrd_start_t;


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