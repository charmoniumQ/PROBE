#define _GNU_SOURCE

#include "pthread_helper.h"

#include <stdlib.h>

#include "debug_logging.h"
#include "global_state.h"

void* pthread_helper(void* restrict uncasted_arg) {
    DEBUG("Intercepting new child pthread");
    ensure_thread_initted();
    struct PthreadHelperArg* pthread_helper_arg = uncasted_arg;
    void* ret = pthread_helper_arg->start_routine(pthread_helper_arg->arg);
    free(pthread_helper_arg);
    return ret;
}

int thrd_helper(void* restrict uncasted_arg) {
    DEBUG("Intercepting new child ISO C thread");
    ensure_thread_initted();
    struct ThrdHelperArg* thrd_helper_arg = uncasted_arg;
    int ret = thrd_helper_arg->func(thrd_helper_arg->arg);
    free(thrd_helper_arg);
    return ret;
}
