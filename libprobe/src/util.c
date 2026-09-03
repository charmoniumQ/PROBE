#include "util.h" // for BORROWED, OWNED, CHECK_SNPRINTF

#include <dirent.h> // for dirent
#include <fcntl.h>  // for O_CREAT, AT_FDCWD, F_GETFD, O_R...
#include <immintrin.h>
#include <limits.h> // IWYU pragma: keep for PATH_MAX, SSIZE_MAX
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>   // for malloc
#include <string.h>   // for memcpy
#include <sys/stat.h> // for S_IFDIR, S_IFMT, statx, STATX_TYPE
#include <sys/sysmacros.h>
#include <sys/types.h> // for ssize_t, off_t
// IWYU pragma: no_include "asm-generic/errno-base.h"   for EBADF
// IWYU pragma: no_include "bits/posix1_lim.h"          for SSIZE_MAX
// IWYU pragma: no_include "linux/limits.h"             for PATH_MAX
// IWYU pragma: no_include "linux/stat.h"               for statx, STATX_TYPE

#include "../generated/libc_hooks.h" // for client_...
#include "debug_logging.h"           // for EXPECT, EXPECT_NONNULL, LOG
#include "probe_libc.h"              // for probe_libc_...

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

    while ((entry = readdir(dir))) {
        if (entry->d_type == DT_DIR) {
            char path[1024];
            if (probe_libc_memcmp(entry->d_name, ".", 2) == 0 ||
                probe_libc_memcmp(entry->d_name, "..", 3) == 0)
                continue;
            CHECK_SNPRINTF(path, ((int)sizeof(path)), "%s/%s", name, entry->d_name);
            LOG("... ", "%*s%s/", indent, "", entry->d_name);
            list_dir(path, indent + 2);
        } else {
            LOG("... ", "%*s%s\n", indent, "", entry->d_name);
        }
    }
    client_closedir(dir);
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

void print_open_fd(int fd) {
    struct stat st;
    if (client_fstat(fd, &st) == -1) {
        DEBUG("fd %d -> unknown stat", fd);
        return;
    }

    char proc_path[64];
    char target[PATH_MAX];
    snprintf(proc_path, sizeof(proc_path), "/proc/self/fd/%d", fd);
    ssize_t len = client_readlink(proc_path, target, sizeof(target) - 1);
    if (len == -1) {
        DEBUG("fd %d -> path=unknown, device=%u,%u inode=%zu", fd, major(st.st_dev),
              minor(st.st_dev), st.st_ino);
        return;
    }

    target[len] = '\0';

    DEBUG("fd %d -> path=%s, device=%u,%u inode=%zu", fd, target, major(st.st_dev),
          minor(st.st_dev), st.st_ino);
}

static const uint64_t LCG_A = 6364136223846793005ULL;
static const uint64_t LCG_C = 1442695040888963407ULL;

/* Scalar fallback */
__attribute__((target("default"))) void random_bytes_scalar(struct RngState* restrict rng,
                                                            void* restrict buf, size_t n) {
    uint8_t* restrict p = buf;

    while (n >= 8) {
        rng->state[0] = rng->state[0] * LCG_A + LCG_C;

        memcpy(p, &rng->state[0], 8);

        p += 8;
        n -= 8;
    }

    if (n) {
        rng->state[0] = rng->state[0] * LCG_A + LCG_C;

        memcpy(p, &rng->state[0], n);
    }
}

/* AVX-512 version */
__attribute__((target("avx512f,avx512dq"))) void random_bytes_avx512(struct RngState* restrict rng,
                                                                     void* restrict buf, size_t n) {
    uint8_t* restrict p = buf;

    const __m512i a = _mm512_set1_epi64(LCG_A);
    const __m512i c = _mm512_set1_epi64(LCG_C);

    /*
     * Load the eight LCG states once.
     */
    __m512i state = _mm512_loadu_si512(rng->state);

    while (n >= 64) {
        state = _mm512_add_epi64(_mm512_mullo_epi64(state, a), c);

        _mm512_storeu_si512(p, state);

        p += 64;
        n -= 64;
    }

    /*
     * Generate one more vector for the tail, but don't write
     * beyond the requested buffer.
     */
    if (n) {
        state = _mm512_add_epi64(_mm512_mullo_epi64(state, a), c);

        memcpy(p, &state, n);
    }

    /*
     * Write the final eight states back exactly once.
     */
    _mm512_storeu_si512(rng->state, state);
}

void random_bytes(struct RngState* restrict rng, void* restrict buf, size_t n) {
    if (__builtin_cpu_supports("avx512dq"))
        random_bytes_avx512(rng, buf, n);
    else
        random_bytes_scalar(rng, buf, n);
}
