#define _GNU_SOURCE

#include <dirent.h>       // for dirent
#include <errno.h>        // for errno, EBADF
#include <fcntl.h>        // for O_CREAT, AT_FDCWD, F_GETFD, O_R...
#include <limits.h>       // IWYU pragma: keep for PATH_MAX, SSIZE_MAX
#include <stdbool.h>      // for bool, false
#include <stdlib.h>       // for malloc
#include <string.h>       // for memcpy, strcmp, strlen
#include <sys/sendfile.h> // for sendfile
#include <sys/stat.h>     // for S_IFDIR, S_IFMT, statx, STATX_TYPE
#include <sys/types.h>    // for ssize_t, off_t
#include <unistd.h>       // for write
// IWYU pragma: no_include "asm-generic/errno-base.h"   for EBADF
// IWYU pragma: no_include "bits/posix1_lim.h"          for SSIZE_MAX
// IWYU pragma: no_include "linux/limits.h"             for PATH_MAX
// IWYU pragma: no_include "linux/stat.h"               for statx, STATX_TYPE

#include "../generated/libc_hooks.h" // for unwrapped_close, unwrapped_openat
#include "debug_logging.h"           // for EXPECT, EXPECT_NONNULL, LOG
#include "util.h"                    // for BORROWED, OWNED, CHECK_SNPRINTF

bool is_dir(const char* dir) {
    struct statx statx_buf;
    int statx_ret = unwrapped_statx(AT_FDCWD, dir, 0, STATX_TYPE, &statx_buf);
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
    const char* ret = unwrapped_realpath(dirfd_proc_path, resolved_buffer);
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
    memcpy(path_buf, left, left_size);
    path_buf[left_size] = '/';
    memcpy(path_buf + left_size + 1, right, right_size);
    path_buf[left_size + 1 + right_size] = '\0';
    return path_buf;
}

int fd_is_valid(int fd) { return unwrapped_fcntl(fd, F_GETFD) != -1 || errno != EBADF; }

void list_dir(const char* name, int indent) {
    // https://stackoverflow.com/a/8438663
    DIR* dir;
    struct dirent* entry;

    if (!(dir = unwrapped_opendir(name)))
        return;

    while ((entry = unwrapped_readdir(dir))) {
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
    unwrapped_closedir(dir);
}

int copy_file(int src_dirfd, const char* src_path, int dst_dirfd, const char* dst_path,
              ssize_t size) {
    /*
    ** Adapted from:
    ** https://stackoverflow.com/a/2180157
     */
    int src_fd = unwrapped_openat(src_dirfd, src_path, O_RDONLY);
    if (src_fd == -1)
        return -1;
    int dst_fd = unwrapped_openat(dst_dirfd, dst_path, O_WRONLY | O_CREAT, 0666);
    if (dst_fd == -1)
        return -1;
    off_t copied = 0;
    while (copied < size) {
        ssize_t written = sendfile(dst_fd, src_fd, &copied, SSIZE_MAX);
        if (written < 0)
            return -1;
        copied += written;
    }

    EXPECT(== 0, unwrapped_close(src_fd));
    EXPECT(== 0, unwrapped_close(dst_fd));

    return 0;
}

void write_bytes(int dirfd, const char* path, const char* content, ssize_t size) {
    int fd = EXPECT(> 0, unwrapped_openat(dirfd, path, O_RDWR | O_CREAT, 0666));
    ssize_t copied = 0;
    while (copied < size) {
        copied += EXPECT(> 0, write(fd, content, size));
    }
    EXPECT(== 0, unwrapped_close(fd));
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

char* const* read_null_delim_file(const char* path, size_t* array_len) {
    int fd = unwrapped_openat(AT_FDCWD, path, O_RDONLY);
    struct statx statx_result;
    EXPECT(== 0, unwrapped_statx(fd, NULL, AT_EMPTY_PATH, STATX_SIZE, &statx_result));
    size_t buffer_len = statx_result.stx_size;
    char* buffer = EXPECT_NONNULL(malloc(buffer_len + 1));
    buffer[buffer_len] = '\0';
    if ((ssize_t)buffer_len != read(fd, buffer, buffer_len)) {
        ERROR("");
    }
    EXPECT(== 0, unwrapped_close(fd));
    *array_len = 1;
    for (size_t buffer_idx = 0; buffer_idx < buffer_len; ++buffer_idx) {
        if (buffer[buffer_idx] == '\0') {
            ++*array_len;
        }
    }
    char** array = EXPECT_NONNULL(malloc((*array_len + 1) * sizeof(char*)));
    array[*array_len] = NULL;
    size_t buffer_idx = 0;
    size_t array_idx = 0;
    while (true) {
        array[array_idx] = &buffer[buffer_idx];
        if (array_idx + 1 == *array_len) {
            break;
        }
        while (buffer[buffer_idx]) {
            ++buffer_idx;
        }
        ++buffer_idx;
        ASSERTF(buffer_idx < buffer_len, "%ld < %ld; %ld < %ld", buffer_idx, buffer_len, array_idx,
                *array_len);
    }
    return array;
}
