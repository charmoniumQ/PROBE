#define _GNU_SOURCE

#include "pthread_helper.h"

#include <stdlib.h>

#include "global_state.h"

void* pthread_helper(void* restrict arg) {
    ensure_thread_initted();
    struct PthreadHelperArg* real_arg = arg;
    void* ret = real_arg->start_routine(real_arg->arg);
    free(real_arg);
    return ret;
}

int thrd_helper(void* restrict arg) {
    ensure_thread_initted();
    struct ThrdHelperArg* real_arg = arg;
    int ret = real_arg->func(real_arg->arg);
    free(real_arg);
    return ret;
}
