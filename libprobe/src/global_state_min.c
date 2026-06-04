#include "../generated/libc_hooks.h"  // for client_...
#include "global_state.h"

pid_t get_tid_safe() { return 0; }

ExecEpoch get_exec_epoch_safe() { return 0; }

pid_t get_pid_safe() { return 0; }

void exit_with_backup(int status) {
    __asm__ volatile (
        "mov $60, %%rax\n"   // syscall number: exit
        "mov %0, %%rdi\n"   // first argument: status
        "syscall\n"
        :
        : "r"((long)status)
        : "%rax", "%rdi"
    );
    __builtin_unreachable();
}

void init_after_fork() {}

static bool __is_inited;
void ensure_thread_initted() {
    if (!__is_inited) {
        init_function_pointers();
        __is_inited = true;
    }
}
