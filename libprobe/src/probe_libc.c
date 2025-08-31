#define _GNU_SOURCE

#include "probe_libc.h"

#include <errno.h>       // IWYU pragma: keep for ENOENT, ENOMEM
#include <fcntl.h>       // for O_RDONLY, O_CLOEXEC
#include <linux/prctl.h> // for PR_*
#include <stddef.h>      // for size_t, NULL
#include <stdint.h>      // for uint64_t, uintptr_t, int_fast16_t
#include <stdio.h>       // for sprintf
#include <stdlib.h>      // for malloc
#include <sys/auxv.h>    // IWYU pragma: keep for AT_NULL, AT_PAGESZ
#include <sys/syscall.h> // for SYS_dup, SYS_exit, SYS_getcwd
#include <unistd.h>      // IWYU pragma: keep for getpid, gettid
// IWYU pragma: no_include "asm-generic/errno-base.h" for ENOENT, ENOMEM
// IWYU pragma: no_include "elf.h" for AT_NULL, AT_PAGESZS

#include "../src/debug_logging.h" // for DEBUG, ERROR
#ifndef UNIT_TESTS
#include "../generated/libc_hooks.h" // for client_exit, client_strerror
#else
// our unit test framework uses a typical (sane) linking scheme and is allowed
// to liberally use libc so we just alias any libprobe functions we use
#define client_strerror strerror
#define client_exit exit
#define get_pid_safe getpid
// HACK: exec epoch doesn't mean anything outside libprobe
#define get_exec_epoch_safe getpid
#define get_tid_safe gettid
#endif

#define OK(x) {.error = 0, .value = (x)}
#define ERR(e) {.error = (e)}

#define SYSCALL_ERROR_RESULT(res_type, value)                                                      \
    ({                                                                                             \
        if ((value) < 0) {                                                                         \
            return (res_type)ERR(-(value));                                                        \
        }                                                                                          \
        return (res_type)OK((value));                                                              \
    })

#define SYSCALL_ERROR_OPTION(value)                                                                \
    ({                                                                                             \
        if ((value) < 0) {                                                                         \
            return -(value);                                                                       \
        }                                                                                          \
        return 0;                                                                                  \
    })

#define TRY_CLOSE(fd, path)                                                                        \
    ({                                                                                             \
        result ret = probe_libc_close(fd);                                                         \
        if (ret) {                                                                                 \
            WARNING("failed to close fd " path "with error: %s (%d)",                              \
                    strerror_with_backup((int)ret), ret);                                          \
        }                                                                                          \
    })

// HACK: technically the size of the auxiliary vector isn't defined, but muslc
// uses a size_t[38] to store the values of the auxiliary vector (index
// addressed)
#define AUX_CNT 38
size_t auxilary[AUX_CNT] = {0};

char** probe_environ = NULL;
char* environ_buf = NULL;

#if defined(__x86_64__) && defined(__linux__)
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
#endif

// TODO: consider a warning to stderr on failure; needs to be implemented with
// raw syscalls, since calling any fallible code could cause infinite recursion
void exit_with_backup(int status) {
    if (client_exit) {
        client_exit(status);
    }
    probe_syscall1(SYS_exit, status);
    __builtin_unreachable();
}

// 9 bytes from the format string, max 20 bytes from stringing a 64-bit
// integer, 1 for null byte, and two for good luck (and alignment)
#define STRERROR_BUFFER 32
char* strerror_with_backup(int errnum) {
    static char backup_strerror_buf[STRERROR_BUFFER];
    if (client_strerror) {
        return client_strerror(errnum);
    }

    snprintf(backup_strerror_buf, STRERROR_BUFFER, "[ERRNO: %d]", errnum);
    return backup_strerror_buf;
}
#undef STRERROR_BUFFER

static inline result_ssize_t probe_read_all(int fd, void* buf, size_t n) {
    ssize_t total = 0;
    result_ssize_t curr;
    do {
        curr = probe_libc_read(fd, buf, n - total);
        if (curr.error) {
            return curr;
        }
        total += curr.value;
    } while (curr.value > 0);
    return (result_ssize_t)OK(total);
}

// TODO: better error handling that specifies *where* something went wrong;
// some debug statements would be good too, but want to keep the file
// compileable with -DUNIT_TESTS for well... unit tests
result probe_libc_init(void) {
    // auxiliary vector initialization
    {
        typedef struct {
            size_t key;
            size_t val;
        } aux_entry;

        aux_entry tmp;
        ssize_t size = probe_syscall5(SYS_prctl, PR_GET_AUXV, (uintptr_t)&tmp, /*size*/ 0, 0, 0);
        if (size < 0) {
            // the only listed error condition for PR_GET_AUXV is EFAULT for an
            // invalid address, so an error here implies some kind of kernel
            // state corruption
            ERROR("failed to PR_GET_AUXV; something is broken in the kernel");
        }

        aux_entry* buf = calloc(size, 1);
        if (buf == NULL) {
            WARNING("falied to allocate buffer for auxilary vector");
            return ENOMEM;
        }
        size = probe_syscall5(SYS_prctl, PR_GET_AUXV, (uintptr_t)buf, size, 0, 0);
        if (size < 0) {
            ERROR("failed to PR_GET_AUXV; either calloc or the kernel is corrupted");
        }

        size_t entries = (size / sizeof(aux_entry));
        for (size_t i = 0; i < entries && i < AUX_CNT; ++i) {
            auxilary[buf[i].key] = buf[i].val;
        }
        free(buf);
    }

    // probe_environ initialization
    {
        if (probe_environ != NULL) {
            free(probe_environ);
            probe_environ = NULL;
        }
        if (environ_buf != NULL) {
            free(environ_buf);
            environ_buf = NULL;
        }

        result_int environ_fd = probe_libc_open("/proc/self/environ", O_RDONLY | O_CLOEXEC, 0);
        if (environ_fd.error) {
            WARNING("Unable to open /proc/self/environ: (%d) %s", environ_fd.error,
                    strerror_with_backup(environ_fd.error));
            return environ_fd.error;
        }

        static const size_t INCREMENT = 4096;
        size_t size = INCREMENT;
        size_t total_bytes = 0;
        result_ssize_t read_ret;

        environ_buf = calloc(size, sizeof(char));
        if (environ_buf == NULL) {
            WARNING("Unable to calloc environ buffer");
            return ENOMEM;
        }
        read_ret = probe_read_all(environ_fd.value, environ_buf, size);
        if (read_ret.error) {
            WARNING("Unable to read environ: (%d) %s", read_ret.error,
                    strerror_with_backup(read_ret.error));
            TRY_CLOSE(environ_fd.value, "/proc/self/environ");
            return read_ret.error;
        }
        total_bytes += read_ret.value;
        // this means that there's still more environ to grab, so we'll realloc
        // it and try copying another chunk
        while (read_ret.value == INCREMENT) {
            size += INCREMENT;
            void* new = realloc(environ_buf, size);
            if (new == NULL) {
                WARNING("Unable to realloc environ buffer");
                TRY_CLOSE(environ_fd.value, "/proc/self/environ");
                return ENOMEM;
            }
            environ_buf = new;
            read_ret = probe_read_all(
                environ_fd.value, (void*)((uintptr_t)environ_buf + (size - INCREMENT)), INCREMENT);
            if (read_ret.error) {
                WARNING("Unable to read environ buffer: (%d) %s", read_ret.error,
                        strerror_with_backup(read_ret.error));
                TRY_CLOSE(environ_fd.value, "/proc/self/environ");
                return read_ret.error;
            }
            total_bytes += read_ret.value;
        }
        TRY_CLOSE(environ_fd.value, "/proc/self/environ");

        size_t env_count = 0;
        for (size_t i = 0; i < total_bytes; ++i) {
            if (environ_buf[i] == '\0') {
                ++env_count;
            }
        }

        probe_environ = calloc(env_count + 1, sizeof(char*));
        if (probe_environ == NULL) {
            WARNING("Unable to calloc probe_environ");
            return ENOMEM;
        }

        size_t buf_offset = 0;
        for (size_t i = 0; buf_offset < total_bytes && i < env_count; ++i) {
            probe_environ[i] = environ_buf + buf_offset;
            buf_offset +=
                (probe_libc_strnlen(environ_buf + buf_offset, total_bytes - buf_offset) + 1);
        }
    }

    return 0;
}

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
            return (result_str)ERR(ENOENT);
        }

        return (result_str)OK(buf);
    }
    return (result_str)ERR(-retval);
}

pid_t probe_libc_getpid(void) { return probe_syscall0(SYS_getpid); }

pid_t probe_libc_getppid(void) { return probe_syscall0(SYS_getppid); }

pid_t probe_libc_gettid(void) { return probe_syscall0(SYS_gettid); }

result_int probe_libc_dup(int oldfd) {
    int retval = probe_syscall1(SYS_dup, oldfd);
    SYSCALL_ERROR_RESULT(result_int, retval);
}

result_int probe_libc_open(const char* path, int flags, mode_t mode) {
    ssize_t retval = probe_syscall3(SYS_open, (uintptr_t)path, flags, mode);
    SYSCALL_ERROR_RESULT(result_int, retval);
}

result_int probe_libc_openat(int dirfd, const char* path, int flags, mode_t mode) {
    ssize_t retval = probe_syscall4(SYS_openat, dirfd, (uintptr_t)path, flags, mode);
    SYSCALL_ERROR_RESULT(result_int, retval);
}

result probe_libc_close(int fd) {
    ssize_t retval = probe_syscall1(SYS_close, fd);
    SYSCALL_ERROR_OPTION(retval);
}

result_ssize_t probe_libc_read(int fd, void* buf, size_t count) {
    ssize_t retval = probe_syscall3(SYS_read, fd, (uintptr_t)buf, count);
    SYSCALL_ERROR_RESULT(result_ssize_t, retval);
}

result_ssize_t probe_libc_write(int fd, const void* buf, size_t count) {
    ssize_t retval = probe_syscall3(SYS_write, fd, (uintptr_t)buf, count);
    SYSCALL_ERROR_RESULT(result_ssize_t, retval);
}

result_mem probe_libc_mmap(void* addr, size_t len, int prot, int flags, int fd) {
    ssize_t retval = probe_syscall6(SYS_mmap, (uintptr_t)addr, len, prot, flags, fd, /*offset*/ 0);
    // can't use SYSCALL_ERROR_WRAPPER because of the type coercion
    if (retval < 0) {
        return (result_mem)ERR(-retval);
    }
    return (result_mem)OK((void*)retval);
}

result probe_libc_munmap(void* addr, size_t len) {
    ssize_t retval = probe_syscall2(SYS_munmap, (uintptr_t)addr, len);
    SYSCALL_ERROR_OPTION(retval);
}

result probe_libc_msync(void* addr, size_t len, int flags) {
    ssize_t retval = probe_syscall3(SYS_msync, (uintptr_t)addr, len, flags);
    SYSCALL_ERROR_OPTION(retval);
}

result_ssize_t probe_libc_sendfile(int out_fd, int in_fd, off_t* offset, size_t count) {
    ssize_t retval = probe_syscall4(SYS_sendfile, out_fd, in_fd, (uintptr_t)offset, count);
    SYSCALL_ERROR_RESULT(result_ssize_t, retval);
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
    if (new == NULL) {
        return NULL;
    }
    probe_libc_memcpy(new, s, size);
    new[size] = '\0';
    return new;
}

int probe_libc_strncmp(const char* a, const char* b, size_t n) {
    size_t i = 0;
    for (; a[i] != '\0' && b[i] != '\0' && i < n; ++i) {
        int_fast16_t diff = (int_fast16_t)(unsigned char)a[i] - (int_fast16_t)(unsigned char)b[i];
        if (diff) {
            return diff;
        }
    }
    if ((i == n) || (a[i] == '\0' && b[i] == '\0')) {
        return 0;
    }
    return (int_fast16_t)(unsigned char)a[i] - (int_fast16_t)(unsigned char)b[i];
}

size_t probe_libc_getpagesize(void) { return auxilary[AT_PAGESZ]; }

const char* probe_libc_getenv(const char* name) {
    if (name == NULL) {
        return NULL;
    }

    size_t name_len = probe_libc_strnlen(name, -1);
    for (size_t i = 0; probe_environ[i] != NULL; ++i) {
        const char* curr = probe_environ[i];
        if (probe_libc_strncmp(name, curr, name_len) == 0 && curr[name_len] == '=') {
            return curr + name_len + 1;
        }
    }
    return NULL;
}
