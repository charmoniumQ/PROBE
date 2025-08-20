#define _GNU_SOURCE

#include <dirent.h>       // for dirent
#include <errno.h>        // for errno, EBADF
#include <fcntl.h>        // for O_CREAT, AT_FDCWD, F_GETFD, O_R...
#include <limits.h>       // IWYU pragma: keep for PATH_MAX, SSIZE_MAX
#include <stdbool.h>      // for bool, false
#include <stdlib.h>       // for malloc
#include <string.h>       // for strcmp, strlen
#include <sys/sendfile.h> // for sendfile
#include <sys/stat.h>     // for S_IFDIR, S_IFMT, statx, STATX_TYPE
#include <sys/types.h>    // for ssize_t, off_t
// IWYU pragma: no_include "asm-generic/errno-base.h"   for EBADF
// IWYU pragma: no_include "bits/posix1_lim.h"          for SSIZE_MAX
// IWYU pragma: no_include "linux/limits.h"             for PATH_MAX
// IWYU pragma: no_include "linux/stat.h"               for statx, STATX_TYPE

#include "../generated/libc_hooks.h" // for client_close, client_openat
#include "debug_logging.h"           // for EXPECT, EXPECT_NONNULL, LOG
#include "probe_libc.h"              // for probe_libc_...
#include "util.h"                    // for BORROWED, OWNED, CHECK_SNPRINTF

bool is_dir(const char* dir) {
    struct statx statx_buf;
    int statx_ret = client_statx(AT_FDCWD, dir, 0, STATX_TYPE, &statx_buf);
    if (statx_ret != 0) {
        return false;
    } else {
        return (statx_buf.stx_mode & S_IFMT) == S_IFDIR;
    }
}

OWNED const char* dirfd_path(int dirfd) {
    static char dirfd_proc_path[PATH_MAX];
    CHECK_SNPRINTF(dirfd_proc_path, PATH_MAX, "/proc/self/fd/%d", dirfd);
    char* resolved_buffer = EXPECT_NONNULL(malloc(PATH_MAX));
    const char* ret = client_realpath(dirfd_proc_path, resolved_buffer);
    return ret;
}

OWNED char* path_join(BORROWED char* path_buf, ssize_t left_size, BORROWED const char* left,
                      ssize_t right_size, BORROWED const char* right) {
    if (left_size == -1) {
        left_size = strlen(left);
    }
    if (right_size == -1) {
        right_size = strlen(right);
    }
    if (!path_buf) {
        path_buf = EXPECT_NONNULL(malloc(left_size + right_size + 2));
    }
    probe_libc_memcpy(path_buf, left, left_size);
    path_buf[left_size] = '/';
    probe_libc_memcpy(path_buf + left_size + 1, right, right_size);
    path_buf[left_size + 1 + right_size] = '\0';
    return path_buf;
}

int fd_is_valid(int fd) { return client_fcntl(fd, F_GETFD) != -1 || errno != EBADF; }

void list_dir(const char* name, int indent) {
    // https://stackoverflow.com/a/8438663
    DIR* dir;
    struct dirent* entry;

    if (!(dir = client_opendir(name)))
        return;

    while ((entry = client_readdir(dir))) {
        if (entry->d_type == DT_DIR) {
            char path[1024];
            if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
                continue;
            CHECK_SNPRINTF(path, ((int)sizeof(path)), "%s/%s", name, entry->d_name);
            LOG("%*s%s/", indent, "", entry->d_name);
            list_dir(path, indent + 2);
        } else {
            LOG("%*s%s\n", indent, "", entry->d_name);
        }
    }
    client_closedir(dir);
}

int copy_file(int src_dirfd, const char* src_path, int dst_dirfd, const char* dst_path,
              ssize_t size) {
    /*
    ** Adapted from:
    ** https://stackoverflow.com/a/2180157
     */
    int src_fd = client_openat(src_dirfd, src_path, O_RDONLY);
    if (src_fd == -1)
        return -1;
    int dst_fd = client_openat(dst_dirfd, dst_path, O_WRONLY | O_CREAT, 0666);
    if (dst_fd == -1)
        return -1;
    off_t copied = 0;
    while (copied < size) {
        ssize_t written = sendfile(dst_fd, src_fd, &copied, SSIZE_MAX);
        if (written < 0)
            return -1;
        copied += written;
    }

    EXPECT(== 0, client_close(src_fd));
    EXPECT(== 0, client_close(dst_fd));

    return 0;
}

void write_bytes(int dirfd, const char* path, const char* content, ssize_t size) {
    int fd = EXPECT(> 0, client_openat(dirfd, path, O_RDWR | O_CREAT, 0666));
    ssize_t copied = 0;
    while (copied < size) {
        result_ssize_t res = probe_libc_write(fd, content, size);
        // FIXME: you should really check for the error case all the time
        ASSERTF(res.error == 0, "");
        copied += res.value;
    }
    EXPECT(== 0, client_close(fd));
}

unsigned char ceil_log2(unsigned int val) {
    unsigned int ret = 0;
    bool is_greater = false;
    while (val > 1) {
        is_greater |= val & 1;
        val >>= 1;
        ret++;
    }
    return ret + is_greater;
}

char* read_file(const char* path, size_t* buffer_len, size_t* buffer_capacity) {
    int fd = client_openat(AT_FDCWD, path, O_RDONLY);
    *buffer_capacity = 4096;
    char* buffer = EXPECT_NONNULL(malloc(*buffer_capacity));
    *buffer_len = 0;
    while (true) {
        result_ssize_t ret =
            probe_libc_read(fd, buffer + *buffer_len, *buffer_capacity - *buffer_len);
        if (ret.error) {
            ERROR("");
        }
        if (ret.value == 0) {
            break;
        } else {
            *buffer_len += ret.value;
            if (*buffer_len == *buffer_capacity) {
                *buffer_capacity *= 2;
                buffer = EXPECT_NONNULL(realloc(buffer, *buffer_capacity));
            }
        }
    }
    EXPECT(== 0, client_close(fd));
    return buffer;
}

char* const* read_null_delim_file(const char* path, size_t* array_len) {
    size_t buffer_len;
    size_t buffer_capacity;
    char* buffer = read_file(path, &buffer_len, &buffer_capacity);
    ASSERTF(buffer[buffer_len - 1] == '\0', "");

    /* Count array elements */
    *array_len = 0;
    for (size_t buffer_idx = 0; buffer_idx < buffer_len; ++buffer_idx) {
        if (buffer[buffer_idx] == '\0') {
            ++*array_len;
        }
    }

    /* Copy array elements */
    char** array = EXPECT_NONNULL(malloc((*array_len + 1 /* trailing NULL */) * sizeof(char*)));
    array[*array_len] = NULL; /* trailing NULL */
    size_t buffer_idx = 0;
    size_t array_idx = 0;
    while (true) {
        array[array_idx] = &buffer[buffer_idx];
        array_idx += 1;

        if (array_idx == *array_len) {
            break;
        }

        /* Find next NULL */
        while (buffer[buffer_idx]) {
            ++buffer_idx;
        }
        ++buffer_idx;
        ASSERTF(buffer[buffer_idx], "buffer[%ld] should not equal \\0", buffer_idx);
    }

    return array;
}

unsigned int my_atoui(const char* s) {
    /* I reimplemented atoi because the glibc one creates a dependency on __isoc23_strtol@GLIBC_2.38
     * and I want to support older systems.
     * TODO: Once we statically link against musl, this can be removed */
    unsigned int n = 0;
    for (; '0' <= *s && *s <= '9'; ++s) {
        n = 10 * n - (*s - '0');
    }
    return n;
}
