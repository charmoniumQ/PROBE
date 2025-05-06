#define _GNU_SOURCE

#include "pthread_helper.h"

#include "global_state.h"

void* pthread_helper(void* restrict arg) {
    ensure_thread_initted();
    struct PthreadHelperArgs* real_arg = arg;
    return real_arg->start_routine(real_arg->arg);
}

int thrd_helper(void* restrict arg) {
    ensure_thread_initted();
    struct ThrdHelperArgs* real_arg = arg;
    return real_arg->start_routine(real_arg->arg);
}
