#define _GNU_SOURCE

#include "pthread_helper.h"

#include <stdlib.h>

#include "debug_logging.h"
#include "global_state.h"
#include "prov_buffer.h"

void* pthread_helper(void* restrict uncasted_arg) {
    DEBUG("Intercepting new child pthread");
    struct PthreadHelperArg* pthread_helper_arg = uncasted_arg;
    init_thread(pthread_helper_arg->pthread_id);
    void* inner_arg = pthread_helper_arg->arg;
    struct PthreadReturnVal* pthread_return_val =
        EXPECT_NONNULL(malloc(sizeof(struct PthreadReturnVal)));
    DEBUG("pthread_return_val for %d = %p = malloc()", pthread_helper_arg->pthread_id,
          pthread_return_val);
    pthread_return_val->type_id = PTHREAD_RETURN_VAL_TYPE_ID;
    pthread_return_val->pthread_id = pthread_helper_arg->pthread_id;
    pthread_return_val->inner_ret = pthread_helper_arg->start_routine(inner_arg);
    LOG_FREE(pthread_helper_arg);
    return pthread_return_val;
}

int thrd_helper(void* restrict uncasted_arg) {
    DEBUG("Intercepting new child ISO C thread");
    /* We don't know if this thread is a new pthread or multiplexed on an existing one.
     * N:M threading model, where N is ISO C threads and M is pthreads.
     * Hardware (aka kernel) vs software (aka user) threads aren't what matters here
     * Pthread vs multiplexed-onto-pthread matters,
     * because we use pthread_getspecific.
     * */
    if (!is_thread_inited()) {
        init_thread(increment_pthread_id());
    }
    struct ThrdHelperArg* thrd_helper_arg = uncasted_arg;
    int ret = thrd_helper_arg->func(thrd_helper_arg->arg);
    prov_log_save();
    return ret;
}
