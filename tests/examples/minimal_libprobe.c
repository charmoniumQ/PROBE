#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdbool.h>
#include <unistd.h>

//// libprobe/generated/libc_hooks.h ////
static FILE * (*unwrapped_fopen)(const char *filename, const char *opentype);
static pid_t (*unwrapped_fork)();

//// libprobe/src/global_state.c ////
static bool is_process_initted = false;
static __thread bool is_thread_initted = false;

static void ensure_initted() {
    if (!is_thread_initted) {
        if (!is_process_initted) {
            fprintf(stderr, "%d.%d Initializing process\n", getpid(), getpid());
            is_process_initted = true;
            //// libprobe/generated/libc_hooks.c ////
            unwrapped_fopen = dlsym(RTLD_NEXT, "fopen");
            unwrapped_fork = dlsym(RTLD_NEXT, "fork");
        }
        fprintf(stderr, "%d.%d Initializing thread\n", getpid(), gettid());
        is_thread_initted = true;
    }
}

//// libprobe/generated/libc_hooks.c ////
FILE * fopen(const char *filename, const char *opentype) {
    ensure_initted();
    fprintf(stderr, "%d.%d fopen(\"%s\", \"%s\")\n", getpid(), gettid(), filename, opentype);
    FILE * ret = unwrapped_fopen(filename, opentype);
    return ret;
}

pid_t fork() {
    ensure_initted();
    fprintf(stderr, "%d.%d fork()\n", getpid(), gettid());
    pid_t ret = unwrapped_fork();
    return ret;
}
