#pragma once

#define _GNU_SOURCE

#include <stddef.h>    // for size_t
#include <sys/types.h> // for pid_t, ssize_t, off_t
// IWYU pragma: no_include "unistd.h" for environ

#define ATTR_HIDDEN __attribute__((visibility("hidden")))

// effectively a Result<()>, in standard C convention, 0 for success, >0 for error
typedef int result;

typedef struct {
    int error;
    char* _Nullable value;
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
    void* _Nullable value;
} result_mem;

typedef struct {
    int error;
    size_t size;
    void* _Nullable value;
} result_sized_mem;

// Perhaps, we will do this differently in the future
#define probe_environ environ
extern char* _Nullable* _Nonnull environ;

// calling any probe_libc_* function before you call this *and* it returns zero
// (this will require a functional /proc filesystem) is considered undefined
// behavior, but at time of writing it only actually effects
// probe_libc_getpagesize, probe_libc_getenv, and probe_environ
ATTR_HIDDEN result probe_libc_init(void);

__attribute__((noreturn, visibility("hidden"))) void exit_with_backup(int status);
ATTR_HIDDEN char* _Nonnull strerror_with_backup(int errnum);

ATTR_HIDDEN int probe_libc_memcmp(const void* _Nonnull s1, const void* _Nonnull s2, size_t n);
ATTR_HIDDEN void* _Nonnull probe_libc_memcpy(void* restrict _Nonnull dest,
                                             const void* restrict _Nonnull src, size_t n);
ATTR_HIDDEN void* _Nonnull probe_libc_memset(void* _Nonnull s, int c, size_t n);
ATTR_HIDDEN size_t probe_libc_memcount(const char* _Nonnull s, size_t maxlen, char delim);

ATTR_HIDDEN result_str probe_libc_getcwd(char* _Nonnull buf, size_t size);

ATTR_HIDDEN pid_t probe_libc_getpid(void);
ATTR_HIDDEN pid_t probe_libc_getppid(void);
ATTR_HIDDEN pid_t probe_libc_gettid(void);

ATTR_HIDDEN result_int probe_libc_openat(int dirfd, const char* _Nullable path, int flags,
                                         mode_t mode);

/*
 * There is nothing useful to do with an error on close.
 * Like the majestic honeybadger, the program just print a warning and keep going anyway.
 * If everyone handles it the same way, we might as well handle it here, to avoid code duplication.
 * Then close should return void.
 */
ATTR_HIDDEN void probe_libc_close(int fd);
ATTR_HIDDEN result probe_libc_ftruncate(int fd, off_t length);
ATTR_HIDDEN result probe_libc_statx(int dirfd, const char* _Nullable restrict path, int flags,
                                    unsigned int mask, void* _Nonnull restrict statxbuf);
ATTR_HIDDEN result probe_libc_mkdirat(int dirfd, const char* _Nonnull path, mode_t mode);

// implementing the flags parameter without soundness bugs requires using the
// faccessat2 syscall under the hood, which was only added in 2020, and we're
// not using it anywhere, so it's just been omitted
ATTR_HIDDEN result probe_libc_faccessat(int dirfd, const char* _Nonnull path, int mode);

// normally arg is a vararg, can be set to 0 for ops that don't use it
ATTR_HIDDEN result_int probe_libc_fcntl(int fd, int op, unsigned long arg);

ATTR_HIDDEN result_ssize_t probe_read_all(int fd, void* _Nonnull buf, size_t n);
ATTR_HIDDEN result_sized_mem probe_read_all_alloc(int fd);
ATTR_HIDDEN result_sized_mem probe_read_all_alloc_path(int dirfd, const char* _Nonnull path);
ATTR_HIDDEN result probe_copy_file(int src_dirfd, const char* _Nullable src_path, int dst_dirfd,
                                   const char* _Nullable dst_path, ssize_t size);

// yes it's missing the offset parameter; it's unclear whether the syscall
// implements offset in bytes or memory pages, and i don't think we actually
// use that feature, so i'll implement it if/when we need it.
ATTR_HIDDEN result_mem probe_libc_mmap(void* _Nullable addr, size_t len, int prot, int flags,
                                       int fd);
ATTR_HIDDEN result probe_libc_munmap(void* _Nonnull addr, size_t len);
ATTR_HIDDEN result probe_libc_msync(void* _Nonnull addr, size_t len, int flags);

ATTR_HIDDEN char* _Nonnull probe_libc_strncpy(char* restrict _Nonnull dest,
                                              const char* restrict _Nonnull src, size_t dsize);
ATTR_HIDDEN size_t probe_libc_strnlen(const char* _Nonnull s, size_t maxlen);
ATTR_HIDDEN char* _Nullable probe_libc_strndup(const char* _Nonnull s, size_t n);
ATTR_HIDDEN int probe_libc_strncmp(const char* _Nonnull a, const char* _Nonnull b, size_t n);
ATTR_HIDDEN size_t probe_libc_strnfind(const char* _Nonnull string, size_t maxlen, char delim);

ATTR_HIDDEN size_t probe_libc_getpagesize(void);

ATTR_HIDDEN const char* _Nullable probe_libc_getenv(const char* _Nonnull name);
