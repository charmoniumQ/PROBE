#define _GNU_SOURCE

#include "../generated/libc_hooks.h"
#include <fcntl.h>
#include <sys/stat.h>
#include <stdlib.h>
#include <limits.h>
#include <string.h>
#include <sys/sendfile.h>
#include <unistd.h>

#include "debug_logging.h"

#include "util.h"

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

OWNED char* path_join(BORROWED char* path_buf, ssize_t left_size, BORROWED const char* left, ssize_t right_size, BORROWED const char* right) {
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

int fd_is_valid(int fd) {
    return unwrapped_fcntl(fd, F_GETFD) != -1 || errno != EBADF;
}

void list_dir(const char* name, int indent) {
    // https://stackoverflow.com/a/8438663
    DIR *dir;
    struct dirent *entry;

    if (!(dir = unwrapped_opendir(name)))
        return;

    while ((entry = unwrapped_readdir(dir))) {
        if (entry->d_type == DT_DIR) {
            char path[1024];
            if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
                continue;
            snprintf(path, sizeof(path), "%s/%s", name, entry->d_name);
            LOG("%*s%s/", indent, "", entry->d_name);
            list_dir(path, indent + 2);
        } else {
            LOG("%*s%s", indent, "", entry->d_name);
        }
    }
    unwrapped_closedir(dir);
}

int copy_file(int src_dirfd, const char* src_path, int dst_dirfd, const char* dst_path, ssize_t size) {
    /*
    ** Adapted from:
    ** https://stackoverflow.com/a/2180157
     */
    int src_fd = unwrapped_openat(src_dirfd, src_path, O_RDONLY);
    if (src_fd == -1) return -1;
    int dst_fd = unwrapped_openat(dst_dirfd, dst_path, O_WRONLY | O_CREAT, 0666);
    if (dst_fd == -1) return -1;
    off_t copied = 0;
    while (copied < size) {
        ssize_t written = sendfile(dst_fd, src_fd, &copied, SSIZE_MAX);
        if (written < 0) return -1;
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
