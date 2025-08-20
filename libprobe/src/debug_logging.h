#pragma once

#define _GNU_SOURCE

#include "global_state.h" // for get_exec_epoch_safe, get_pid_safe, get_tid...
#include <errno.h>        // for errno
#include <stdio.h>        // for fprintf, stderr
#include <stdlib.h>       // for exit, free
#include <string.h>       // for strerror, strndup


#ifndef NDEBUG
#define DEBUG_LOG 1
#else
#endif

#ifndef SOURCE_VERSION
#define SOURCE_VERSION ""
#endif

#define LOG(str, ...)                                                                              \
    fprintf(stderr, "" SOURCE_VERSION " %d.%d.%d " __FILE__ ":%d:%s(): " str "\n", get_pid_safe(), \
            get_exec_epoch_safe(), get_tid_safe(), __LINE__, __func__, ##__VA_ARGS__)

#ifdef DEBUG_LOG
#define DEBUG(str, ...) LOG("DEBUG " str, ##__VA_ARGS__)
#else
#define DEBUG(...)
#endif

#define WARNING(str, ...) LOG("WARNING " str " (errno=%d)", ##__VA_ARGS__, errno)

/* TODO: replace assert with ASSERTF because ASSERTF calls unwrapped_exit() */
#define ERROR(str, ...)                                                                            \
    ({                                                                                             \
        char* errno_str = strndup(strerror_with_backup(errno), 4096);                              \
        LOG("ERROR " str " (errno=%d %s)", ##__VA_ARGS__, errno, errno_str);                       \                                                                      \
        exit_with_backup(103);                                                                     \
    })

/* TODO: Replace EXPECT, ASSERTF, NOT_IMPLEMENTED with explicit error handling: { ERR(...); return -1; } */
#ifndef NDEBUG
#define ASSERTF(cond, str, ...)                                                                    \
    ({                                                                                             \
        if (__builtin_expect(!(cond), 0)) {                                                        \
            ERROR("Assertion " #cond " failed: " str, ##__VA_ARGS__);                              \
        }                                                                                          \
    })
/* TODO: rewrite this as (const_val, binary_op, expr) */
#define EXPECT(cond, expr)                                                                         \
    ({                                                                                             \
        errno = 0;                                                                                 \
        ssize_t ret = (expr);                                                                      \
        ASSERTF((ret cond), "Expected " #expr #cond ", but " #expr " == %ld", ret);                \
        ret;                                                                                       \
    })
#define EXPECT_NONNULL(expr)                                                                       \
    ({                                                                                             \
        errno = 0;                                                                                 \
        void* ret = (expr);                                                                        \
        ASSERTF(ret, "Expected non-null pointer from " #expr);                                     \
        ret;                                                                                       \
    })
#else
#define ASSERTF(...)
#define EXPECT(cond, expr) expr
#define EXPECT_NONNULL(expr) expr
#endif

#define NOT_IMPLEMENTED(str, ...) ERROR("Not implemented: " str, ##__VA_ARGS__)

__attribute__((unused)) static inline void __mark_as_used__debug_logging_h() {
    fprintf(stderr, "hi");
    strndup("hi", 3);
    get_pid();
    exit(1);
}
