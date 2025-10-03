#define _GNU_SOURCE
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <unistd.h>

bool initialized = false;

#define SYSCALL_REG(reg) register uint64_t reg __asm__(#reg)

uint64_t probe_syscall0(uint64_t sysnum) {
    SYSCALL_REG(rax) = sysnum;

    __asm__ __volatile__("syscall" : "+r"(rax) : : "memory", "cc", "rcx", "r11");

    return rax;
}

pid_t probe_libc_getpid(void) { return probe_syscall0(SYS_getpid); }

pid_t probe_libc_getppid(void) { return probe_syscall0(SYS_getppid); }

pid_t probe_libc_gettid(void) { return probe_syscall0(SYS_gettid); }

void __attribute__ ((constructor)) setup() {
    printf("constructor %d=%d %d=%d %d\n", getpid(), probe_libc_getpid(), gettid(), probe_libc_gettid(), initialized);
    initialized = true;
}
