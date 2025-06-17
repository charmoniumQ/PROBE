#include "sys/syscall.h"
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdbool.h>
#include <unistd.h>
#include <syscall.h>
#include <fcntl.h>

//// libprobe/generated/libc_hooks.h ////
static FILE * (*unwrapped_fopen)(const char *filename, const char *opentype);
static pid_t (*unwrapped_fork)();

//// libprobe/src/global_state.c ////
static bool is_process_initted = false;
static __thread bool is_thread_initted = false;

#define ENVP_SIZE 256

int noop() { return 0; }

__attribute__((__weak__)) void _init();
__attribute__((__weak__)) void _fini();

int fake_argc = 1;
char* fake_argv[2] = { "PROBE", 0 };
char* fake_envp[ENVP_SIZE] = { 0 };

// int __libc_start_main(int (*)(), int, char **, void (*)(), void(*)(), void(*)());
typedef int lsm2_fn(int (*)(int,char **,char **), int, char **);
int libc_start_main_stage2(int (*main)(int,char **,char **), int argc, char **argv);
long __syscall(long, ...);
// lsm2_fn libc_start_main_stage2;

void __init_libc(char **envp, char *pn);



static void ensure_initted() {
    if (!is_thread_initted) {
        if (!is_process_initted) {

            syscall(SYS_write, STDERR_FILENO, (size_t)"testmsg\n", 8);


            int auxv_fd = syscall(SYS_open, "/proc/self/auxv", O_RDONLY, 0);
            if (auxv_fd == -1) { // then open failed
                static const char err_msg[] = "PROBE: unable to open /proc/self/auxv, aborting";
                syscall(SYS_write, STDERR_FILENO, err_msg, sizeof(err_msg));
                syscall(SYS_exit, -1);
            }

            long i = 0;
            long bytes_read = 0;
            do {
                bytes_read = syscall(SYS_read, auxv_fd, fake_envp+i+1, ENVP_SIZE - i);
                i += bytes_read;
            } while (bytes_read <= 0);

            syscall(SYS_close, auxv_fd);




            __init_libc(fake_envp, fake_argv[0]);

            /* Barrier against hoisting application code or anything using ssp
             * or thread pointer prior to its initialization above. */
            lsm2_fn *stage2 = libc_start_main_stage2;
            __asm__ ( "" : "+r"(stage2) : : "memory" );

            stage2(noop, 1, fake_argv);



            fprintf(stderr, "%d.%d Initializing process\n", getpid(), getpid());
            is_process_initted = true;
            //// libprobe/generated/libc_hooks.c ////
            unwrapped_fopen = dlsym(RTLD_NEXT, "fopen");
            if (!unwrapped_fopen) fprintf(stderr, "%s\n", dlerror());
            unwrapped_fork = dlsym(RTLD_NEXT, "fork");
            if (!unwrapped_fork) fprintf(stderr, "%s\n", dlerror());
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
