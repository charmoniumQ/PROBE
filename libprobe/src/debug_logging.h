#pragma once

#define _GNU_SOURCE

#include <stdio.h>
#include "util.h"
#include "global_state.h"

#ifndef NDEBUG
#define DEBUG_LOG 1
#else
#endif

#ifndef SOURCE_VERSION
#define SOURCE_VERSION ""
#endif

#define LOG(str, ...) fprintf(stderr, "" SOURCE_VERSION ":" __FILE__ ":%d:%s() pid=%d.%d.%d " str "\n", __LINE__, __func__, get_pid_safe(), get_exec_epoch_safe(), get_tid_safe(), ##__VA_ARGS__)

#ifdef DEBUG_LOG
#define DEBUG(str, ...) LOG("DEBUG " str, ##__VA_ARGS__)
#else
#define DEBUG(...)
#endif

#define ERROR(str, ...) ({ LOG("ERROR " str " (errno=%d)", ##__VA_ARGS__, errno); exit(1); })

/* TODO: Replace EXPECT, ASSERTF, NOT_IMPLEMENTED with explicit error handling: { ERR(...); return -1; } */
#ifndef NDEBUG
#define ASSERTF(cond, str, ...) ({ \
    if (UNLIKELY(!(cond))) { \
        ERROR("Assertion " #cond " failed: " str, ##__VA_ARGS__); \
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

#define NOT_IMPLEMENTED(str, ...) ERROR("Not implemented: " str, ##__VA_ARGS__)
