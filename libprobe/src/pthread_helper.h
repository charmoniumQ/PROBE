#pragma once

#define _GNU_SOURCE

struct PthreadHelperArg {
    void* (*start_routine)(void*);
    void* restrict arg;
};

__attribute__((visibility("hidden"))) void* pthread_helper(void* restrict arg);

struct ThrdHelperArg {
    int (*func)(void*);
    void* restrict arg;
};

__attribute__((visibility("hidden"))) int thrd_helper(void* restrict arg);
