#pragma once

#include <stdint.h>

#define _GNU_SOURCE

struct PthreadHelperArg {
    void* (*start_routine)(void*);
    uint16_t pthread_id;
    void* restrict arg;
};

static const uint64_t PTHREAD_RETURN_VAL_TYPE_ID = 0x9fc84cce961fbf9f;

struct PthreadReturnVal {
    /* Should be always set to PTHREAD_RETURN_VAL_TYPE_ID.
     * This helps us know that the rest of the struct was set by us. */
    uint64_t type_id;

    uint16_t pthread_id;
    void* inner_ret;
};

void* pthread_helper(void* restrict arg);

struct ThrdHelperArg {
    int (*func)(void*);
    void* restrict arg;
};

int thrd_helper(void* restrict arg);
