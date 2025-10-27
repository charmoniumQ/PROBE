#define _GNU_SOURCE

#include <dirent.h>    // for dirent
#include <fcntl.h>     // for O_CREAT, AT_FDCWD, F_GETFD, O_R...
#include <limits.h>    // IWYU pragma: keep for PATH_MAX, SSIZE_MAX
#include <stdbool.h>   // for bool, false
#include <stdlib.h>    // for malloc
#include <sys/stat.h>  // for S_IFDIR, S_IFMT, statx, STATX_TYPE
#include <sys/types.h> // for ssize_t, off_t
// IWYU pragma: no_include "asm-generic/errno-base.h"   for EBADF
// IWYU pragma: no_include "bits/posix1_lim.h"          for SSIZE_MAX
// IWYU pragma: no_include "linux/limits.h"             for PATH_MAX
// IWYU pragma: no_include "linux/stat.h"               for statx, STATX_TYPE

#include "../generated/libc_hooks.h" // for client_...
#include "debug_logging.h"           // for EXPECT, EXPECT_NONNULL, LOG
#include "probe_libc.h"              // for probe_libc_...
#include "util.h"                    // for BORROWED, OWNED, CHECK_SNPRINTF

bool is_dir(const char* dir) {
    struct statx statx_buf;
    result statx_ret = probe_libc_statx(AT_FDCWD, dir, 0, STATX_TYPE, &statx_buf);
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
        left_size = probe_libc_strnlen(left, PATH_MAX);
    }
    if (right_size == -1) {
        right_size = probe_libc_strnlen(right, PATH_MAX);
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

int fd_is_valid(int fd) { return probe_libc_fcntl(fd, F_GETFD, 0).error != EBADF; }

void list_dir(const char* name, int indent) {
    // https://stackoverflow.com/a/8438663
    DIR* dir;
    struct dirent* entry;

    if (!(dir = client_opendir(name)))
        return;

    while ((entry = client_readdir(dir))) {
        if (entry->d_type == DT_DIR) {
            char path[1024];
            if (probe_libc_memcmp(entry->d_name, ".", 2) == 0 ||
                probe_libc_memcmp(entry->d_name, "..", 3) == 0)
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
