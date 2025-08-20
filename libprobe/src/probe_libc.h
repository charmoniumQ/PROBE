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

// calling any probe_libc_* function before you call this *and* it returns zero
// (this will require a functional /proc filesystem) is considered undefined
// behavior, but at time of writing it only actually effects
// probe_libc_getpagesize, probe_libc_getenv, and probe_environ
ATTR_HIDDEN result probe_libc_init(void);

extern char** probe_environ;

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

ATTR_HIDDEN result_int probe_libc_open(const char* path, int flags, mode_t mode);
ATTR_HIDDEN result probe_libc_close(int fd);
ATTR_HIDDEN result_ssize_t probe_libc_read(int fd, void* buf, size_t count);
ATTR_HIDDEN result_ssize_t probe_libc_write(int fd, const void* buf, size_t count);

// yes it's missing the offset parameter; it's unclear whether the syscall
// implements offset in bytes or memory pages, and i don't think we actually
// use that feature, so i'll implement it if/when we need it.
ATTR_HIDDEN result_mem probe_libc_mmap(void* addr, size_t len, int prot, int flags, int fd);
ATTR_HIDDEN result probe_libc_munmap(void* addr, size_t len);
ATTR_HIDDEN result probe_libc_msync(void* addr, size_t len, int flags);

ATTR_HIDDEN result_ssize_t probe_libc_sendfile(int out_fd, int in_fd, off_t* offset, size_t count);

ATTR_HIDDEN char* probe_libc_strncpy(char* dest, const char* src, size_t dsize);
ATTR_HIDDEN size_t probe_libc_strnlen(const char* s, size_t maxlen);
ATTR_HIDDEN char* probe_libc_strndup(const char* s, size_t n);
ATTR_HIDDEN int probe_libc_strncmp(const char* a, const char* b, size_t n);
static inline size_t probe_libc_strlen(const char* s) { return probe_libc_strnlen(s, -1); }

ATTR_HIDDEN size_t probe_libc_getpagesize(void);

ATTR_HIDDEN const char* probe_libc_getenv(const char* name);
