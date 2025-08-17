#pragma once

#define _GNU_SOURCE

#include <stddef.h>    // for size_t
#include <sys/types.h> // for pid_t, ssize_t, off_t

#define ATTR_HIDDEN __attribute__((visibility("hidden")))

// effectively a Result<()>, in standard C convention, 0 for success, >0 for error
typedef int result;

typedef struct {
    int error;
    char* value;
} result_str;

typedef struct {
    int error;
    int value;
} result_int;

typedef struct {
    int error;
    ssize_t value;
} result_ssize_t;

typedef struct {
    int error;
    void* value;
} result_mem;

__attribute__((noreturn, visibility("hidden"))) void exit_with_backup(int status);
ATTR_HIDDEN char* strerror_with_backup(int errnum);

ATTR_HIDDEN int probe_libc_memcmp(const void* s1, const void* s2, size_t n);
ATTR_HIDDEN void* probe_libc_memcpy(void* dest, const void* src, size_t n);
ATTR_HIDDEN void* probe_libc_memset(void* s, int c, size_t n);

ATTR_HIDDEN result_str probe_libc_getcwd(char* buf, size_t size);

ATTR_HIDDEN pid_t probe_libc_getpid(void);
ATTR_HIDDEN pid_t probe_libc_getppid(void);
ATTR_HIDDEN pid_t probe_libc_gettid(void);

ATTR_HIDDEN result_int probe_libc_dup(int oldfd);

ATTR_HIDDEN result_ssize_t probe_libc_read(int fd, void* buf, size_t count);
ATTR_HIDDEN result_ssize_t probe_libc_write(int fd, void* buf, size_t count);

ATTR_HIDDEN result_mem probe_libc_mmap(void* addr, size_t len, int prot, int flags, int fd);
ATTR_HIDDEN result probe_libc_munmap(void* addr, size_t len);
ATTR_HIDDEN result probe_libc_msync(void* addr, size_t len, int flags);
