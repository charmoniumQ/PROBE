#define _GNU_SOURCE

#include "probe_libc.h"

// for some reason it wants to use the underlying errno header, but like no.
#include <errno.h>       // IWYU pragma: keep
#include <stddef.h>      // for size_t, NULL
#include <stdint.h>      // for uint64_t, uintptr_t, int_fast16_t
#include <stdio.h>       // for sprintf
#include <stdlib.h>      // for malloc
#include <sys/syscall.h> // for SYS_dup, SYS_exit, SYS_getcwd
// IWYU pragma: no_include "asm-generic/errno-base.h" for ENOENT

#ifndef UNIT_TESTS
#include "../generated/libc_hooks.h" // for client_exit, client_strerror
#endif

#ifndef __x86_64__
#error "syscall shims only defined for x86_64 linux"
#endif

#define SYSCALL_REG(reg) register uint64_t reg __asm__(#reg)

__attribute__((unused)) static uint64_t probe_syscall0(uint64_t sysnum) {
    SYSCALL_REG(rax) = sysnum;

    __asm__ __volatile__("syscall" : "+r"(rax) : : "memory", "cc", "rcx", "r11");

    return rax;
}

__attribute__((unused)) static uint64_t probe_syscall1(uint64_t sysnum, uint64_t arg1) {
    SYSCALL_REG(rax) = sysnum;
    SYSCALL_REG(rdi) = arg1;

    __asm__ __volatile__("syscall" : "+r"(rax) : "r"(rdi) : "memory", "cc", "rcx", "r11");

    return rax;
}

__attribute__((unused)) static uint64_t probe_syscall2(uint64_t sysnum, uint64_t arg1,
                                                       uint64_t arg2) {
    SYSCALL_REG(rax) = sysnum;
    SYSCALL_REG(rdi) = arg1;
    SYSCALL_REG(rsi) = arg2;

    __asm__ __volatile__("syscall" : "+r"(rax) : "r"(rdi), "r"(rsi) : "memory", "cc", "rcx", "r11");

    return rax;
}

__attribute__((unused)) static uint64_t probe_syscall3(uint64_t sysnum, uint64_t arg1,
                                                       uint64_t arg2, uint64_t arg3) {
    SYSCALL_REG(rax) = sysnum;
    SYSCALL_REG(rdi) = arg1;
    SYSCALL_REG(rsi) = arg2;
    SYSCALL_REG(rdx) = arg3;

    __asm__ __volatile__("syscall"
                         : "+r"(rax)
                         : "r"(rdi), "r"(rsi), "r"(rdx)
                         : "memory", "cc", "rcx", "r11");

    return rax;
}

__attribute__((unused)) static uint64_t
probe_syscall4(uint64_t sysnum, uint64_t arg1, uint64_t arg2, uint64_t arg3, uint64_t arg4) {
    SYSCALL_REG(rax) = sysnum;
    SYSCALL_REG(rdi) = arg1;
    SYSCALL_REG(rsi) = arg2;
    SYSCALL_REG(rdx) = arg3;
    SYSCALL_REG(r10) = arg4;

    __asm__ __volatile__("syscall"
                         : "+r"(rax)
                         : "r"(rdi), "r"(rsi), "r"(rdx), "r"(r10)
                         : "memory", "cc", "rcx", "r11");

    return rax;
}

__attribute__((unused)) static uint64_t probe_syscall5(uint64_t sysnum, uint64_t arg1,
                                                       uint64_t arg2, uint64_t arg3, uint64_t arg4,
                                                       uint64_t arg5) {
    SYSCALL_REG(rax) = sysnum;
    SYSCALL_REG(rdi) = arg1;
    SYSCALL_REG(rsi) = arg2;
    SYSCALL_REG(rdx) = arg3;
    SYSCALL_REG(r10) = arg4;
    SYSCALL_REG(r8) = arg5;

    __asm__ __volatile__("syscall"
                         : "+r"(rax)
                         : "r"(rdi), "r"(rsi), "r"(rdx), "r"(r10), "r"(r8)
                         : "memory", "cc", "rcx", "r11");

    return rax;
}

__attribute__((unused)) static uint64_t probe_syscall6(uint64_t sysnum, uint64_t arg1,
                                                       uint64_t arg2, uint64_t arg3, uint64_t arg4,
                                                       uint64_t arg5, uint64_t arg6) {
    SYSCALL_REG(rax) = sysnum;
    SYSCALL_REG(rdi) = arg1;
    SYSCALL_REG(rsi) = arg2;
    SYSCALL_REG(rdx) = arg3;
    SYSCALL_REG(r10) = arg4;
    SYSCALL_REG(r8) = arg5;
    SYSCALL_REG(r9) = arg6;

    __asm__ __volatile__("syscall"
                         : "+r"(rax)
                         : "r"(rdi), "r"(rsi), "r"(rdx), "r"(r10), "r"(r8), "r"(r9)
                         : "memory", "cc", "rcx", "r11");

    return rax;
}

// probe_libc unit testing just #includes this file verbatim, but doesn't link
// other parts of libprobe so we need to exclude externally dependent functions
#ifndef UNIT_TESTS
// TODO: consider a warning to stderr on failure; needs to be implemented with
// raw syscalls, since calling any fallible code could cause infinite recursion
void exit_with_backup(int status) {
    if (client_exit) {
        client_exit(status);
    }
    probe_syscall1(SYS_exit, status);
    __builtin_unreachable();
}

char* strerror_with_backup(int errnum) {
    static char backup_strerror_buf[32];
    if (client_strerror) {
        return client_strerror(errnum);
    }
    // 9 bytes from the format string, max 20 bytes from stringing a 64-bit
    // integer, 1 for null byte, and two for good luck (and alignment)
    sprintf(backup_strerror_buf, "[ERRNO: %d]", errnum);
    return backup_strerror_buf;
}
#endif

int probe_libc_memcmp(const void* s1, const void* s2, size_t n) {
    const unsigned char* c1 = (const unsigned char*)s1;
    const unsigned char* c2 = (const unsigned char*)s2;

    size_t i = 0;
    for (; (i + sizeof(size_t)) < n; i += sizeof(size_t)) {
        if (*((size_t*)(((uintptr_t)c1) + i)) != *((size_t*)(((uintptr_t)c2) + i))) {
            break;
        }
    }
    for (; i < n; ++i) {
        // type coercion is required since the spec requires that the bytes be
        // interpreted as unsigned chars, but negative values are meaningful
        int_fast16_t diff = ((int_fast16_t)c1[i]) - ((int_fast16_t)c2[i]);
        if (diff) {
            return diff;
        }
    }

    return 0;
}

void* probe_libc_memcpy(void* dest, const void* src, size_t n) {
    if (dest == NULL || n == 0) {
        return dest;
    }

    // compiler optimization hint that dest and src may not alias
    // (as specified by man memcpy)
    if (dest == src) {
        __builtin_unreachable();
    }

    size_t i = 0;
    for (; (i + sizeof(size_t)) < n; i += sizeof(size_t)) {
        *((size_t*)(((uintptr_t)dest) + i)) = *((size_t*)(((uintptr_t)src) + i));
    }
    for (; i < n; ++i) {
        ((unsigned char*)dest)[i] = ((unsigned char*)src)[i];
    }

    return dest;
}

void* probe_libc_memset(void* s, int c, size_t n) {
    // OPTIMIZE: vectorize this by generating a size_t of repeated bytes and
    // copying that
    for (size_t i = 0; i < n; ++i) {
        ((unsigned char*)s)[i] = (unsigned char)c;
    }

    return s;
}

result_str probe_libc_getcwd(char* buf, size_t size) {
    int retval = probe_syscall2(SYS_getcwd, (uintptr_t)buf, size);
    if (retval >= 0) {

        // linux may return the string "(unreachable)" under weird
        // circumstances (see getcwd(2) -> VERSIONS -> C library/kernel
        // differences), which without a check might be interpreted as a
        // relative path, breaking the API contract of getcwd; why does it not
        // just return an error code like all the other edgecases?
        // it would seem only god and linus knows
        if (buf[0] != '/') {
            return (result_str){
                .error = ENOENT,
                .value = NULL,
            };
        }

        return (result_str){
            .error = 0,
            .value = buf,
        };
    }
    return (result_str){
        .error = -retval,
        .value = NULL,
    };
}

pid_t probe_libc_getpid(void) { return probe_syscall0(SYS_getpid); }

pid_t probe_libc_getppid(void) { return probe_syscall0(SYS_getppid); }

pid_t probe_libc_gettid(void) { return probe_syscall0(SYS_gettid); }

result_int probe_libc_dup(int oldfd) {
    int retval = probe_syscall1(SYS_dup, oldfd);
    if (retval >= 0) {
        return (result_int){
            .error = 0,
            .value = retval,
        };
    }
    return (result_int){
        .error = -retval,
    };
}

result_ssize_t probe_libc_read(int fd, void* buf, size_t count) {
    ssize_t retval = probe_syscall3(SYS_read, fd, (uintptr_t)buf, count);
    if (retval >= 0) {
        return (result_ssize_t){
            .error = 0,
            .value = retval,
        };
    }
    return (result_ssize_t){
        .error = -retval,
    };
}

result_ssize_t probe_libc_write(int fd, void* buf, size_t count) {
    ssize_t retval = probe_syscall3(SYS_write, fd, (uintptr_t)buf, count);
    if (retval >= 0) {
        return (result_ssize_t){
            .error = 0,
            .value = retval,
        };
    }
    return (result_ssize_t){
        .error = -retval,
    };
}

result_mem probe_libc_mmap(void* addr, size_t len, int prot, int flags, int fd) {
    ssize_t retval = probe_syscall6(SYS_mmap, (uintptr_t)addr, len, prot, flags, fd, /*offset*/ 0);
    if (retval >= 0) {
        return (result_mem){
            .error = 0,
            .value = (void*)retval,
        };
    }
    return (result_mem){
        .error = -retval,
    };
}

result probe_libc_munmap(void* addr, size_t len) {
    ssize_t retval = probe_syscall2(SYS_munmap, (uintptr_t)addr, len);
    if (retval < 0) {
        return -retval;
    }
    return 0;
}

result probe_libc_msync(void* addr, size_t len, int flags) {
    ssize_t retval = probe_syscall3(SYS_msync, (uintptr_t)addr, len, flags);
    if (retval < 0) {
        return -retval;
    }
    return 0;
}

result_ssize_t probe_libc_sendfile(int out_fd, int in_fd, off_t* offset, size_t count) {
    ssize_t retval = probe_syscall4(SYS_sendfile, out_fd, in_fd, (uintptr_t)offset, count);
    if (retval >= 0) {
        return (result_ssize_t){.error = 0, .value = retval};
    }
    return (result_ssize_t){
        .error = -retval,
    };
}

char* probe_libc_strncpy(char* dest, const char* src, size_t dsize) {
    size_t i = 0;
    for (; i < dsize; ++i) {
        if (src[i] == '\0') {
            break;
        }
        dest[i] = src[i];
    }
    for (; i < dsize; ++i) {
        dest[i] = '\0';
    }
    return dest;
}

size_t probe_libc_strnlen(const char* s, size_t maxlen) {
    if (s == NULL) {
        return 0;
    }
    size_t i = 0;
    for (; i < maxlen && s[i] != '\0'; ++i)
        ;
    return i;
}

char* probe_libc_strndup(const char* s, size_t n) {
    size_t size = probe_libc_strnlen(s, n);
    char* new = malloc(size + 1);
    probe_libc_memcpy(new, s, size);
    new[size] = '\0';
    return new;
}
