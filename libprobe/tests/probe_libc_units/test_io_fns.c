
// this exists solely for lsp and will get preprocessed out during build time
#ifndef SRC_INCLUDED
#include <criterion/criterion.h>
#include "probe_libc.h"
#endif

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>


static int mktemp_file(char *out_path, size_t out_cap) {
    // Create a unique temp file we can read/write
    char tmpl[] = "/tmp/probe_libc_tests_XXXXXX";
    int fd = mkstemp(tmpl);
    if (fd >= 0 && out_path && out_cap) {
        strncpy(out_path, tmpl, out_cap - 1);
        out_path[out_cap - 1] = '\0';
    }
    return fd;
}

static size_t read_all(int fd, char *buf, size_t cap) {
    if (lseek(fd, 0, SEEK_SET) == (off_t)-1) return 0;
    size_t total = 0;
    for (;;) {
        ssize_t n = read(fd, buf + total, cap - total);
        if (n <= 0) break;
        total += (size_t)n;
        if (total == cap) break;
    }
    return total;
}

static void write_all(int fd, const void *buf, size_t count) {
    const char *p = buf;
    while (count > 0) {
        ssize_t n = write(fd, p, count);
        if (n < 0) {
            cr_assert_fail("Failed to write to fd: %s", strerror(errno));
        }
        p += n;
        count -= (size_t)n;
    }
    lseek(fd, 0, SEEK_SET);
}

static void fill_pipe_to_eagain(int wfd) {
    // Write until EAGAIN on non-blocking pipe write-end.
    char block[4096];
    memset(block, 'X', sizeof(block));
    for (;;) {
        result_ssize_t n = probe_libc_write(wfd, block, sizeof(block));
        if (n.error) {
            if (n.error == EAGAIN) break;
            // Unexpected error — fail the test here so callers aren't stuck.
            cr_assert_fail("Unexpected error while filling pipe: %s", strerror(n.error));
        }
        if (n.value == 0) {
            // Shouldn't happen on pipes, but avoid infinite loops.
            break;
        }
    }
}



// Basic success case to a regular file.
Test(write, writes_all_bytes_to_regular_file) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    const char msg[] = "hello\n";
    result_ssize_t n = probe_libc_write(fd, msg, sizeof(msg));
    cr_assert_eq(n.error, 0, "probe_libc_write errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, (ssize_t)sizeof(msg), "Expected %zu bytes written, got %zd",
                 sizeof(msg), n.value);

    // Verify file content
    char buf[64] = {0};
    size_t got = read_all(fd, buf, sizeof(buf));
    cr_expect_eq(got, sizeof(msg), "Expected file size %zu, got %zu", sizeof(msg), got);
    cr_expect_arr_eq(buf, msg, sizeof(msg));

    close(fd);
}

// Zero-length writes should succeed and not change content.
Test(write, zero_length_write_returns_zero_and_is_noop) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    const char pre[] = "data";
    cr_assert_eq((ssize_t)write(fd, pre, sizeof(pre)), (ssize_t)sizeof(pre));

    result_ssize_t n = probe_libc_write(fd, "ignored", 0);
    cr_assert_eq(n.error, 0, "probe_libc_write errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, 0, "Zero-length write should return 0, got %zd", n.value);

    char buf[64] = {0};
    size_t got = read_all(fd, buf, sizeof(buf));
    cr_expect_eq(got, sizeof(pre));
    cr_expect_arr_eq(buf, pre, sizeof(pre));

    close(fd);
}


// Invalid fd (negative).
Test(write, invalid_negative_fd_sets_EBADF) {
    const char msg[] = "x";
    result_ssize_t n = probe_libc_write(-1, msg, sizeof(msg));
    cr_expect_eq(n.error, EBADF, "Expected EBADF, got %d (%s)", n.error, strerror(n.error));
}

// Closed fd.
Test(write, closed_fd_sets_EBADF) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);
    close(fd);

    const char msg[] = "x";
    result_ssize_t n = probe_libc_write(fd, msg, sizeof(msg));
    cr_expect_eq(n.error, EBADF, "Expected EBADF on closed fd, got %d (%s)", n.error,
                 strerror(n.error));

}

// Read-only fd.
Test(write, read_only_fd_sets_EBADF) {
    char path[128] = {0};
    int wfd = mktemp_file(path, sizeof(path));
    cr_assert_neq(wfd, -1);
    close(wfd);

    int rfd = open(path, O_RDONLY);
    cr_assert_neq(rfd, -1);
    unlink(path);

    const char msg[] = "x";
    result_ssize_t n = probe_libc_write(rfd, msg, sizeof(msg));
    cr_expect_eq(n.error, EBADF, "Expected EBADF on O_RDONLY fd, got %d (%s)", n.error,
                 strerror(n.error));

    close(rfd);
}

// NULL buffer with non-zero count -> EFAULT (kernel can't read from user memory).
Test(write, null_buffer_nonzero_count_sets_EFAULT) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    result_ssize_t n = probe_libc_write(fd, NULL, 1);
    cr_expect_eq(n.error, EFAULT, "Expected EFAULT for NULL buffer, got %d (%s)", n.error,
                 strerror(n.error));

    close(fd);
}

// O_APPEND semantics: write should append to end regardless of current offset.
Test(write, append_mode_writes_at_end) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);

    const char a[] = "A";
    const char b[] = "B";

    cr_assert_eq((ssize_t)write(fd, a, sizeof(a)), (ssize_t)sizeof(a));

    int afd = open(path, O_WRONLY | O_APPEND);
    cr_assert_neq(afd, -1);
    unlink(path);

    result_ssize_t n = probe_libc_write(afd, b, sizeof(b));
    cr_assert_eq(n.error, 0, "probe_libc_write errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, (ssize_t)sizeof(b), "append write failed: %zd", n.value);

    // Verify "AB"
    char buf[8] = {0};
    size_t got = read_all(fd, buf, sizeof(buf));
    cr_expect_eq(got, sizeof(a) + sizeof(b));
    cr_expect_str_eq(buf, "A\0B\0"); // because we wrote with sizeof including the null terminator

    close(afd);
    close(fd);
}

// Pipe with no reader: should return EPIPE. We ignore SIGPIPE to avoid terminating the process.
Test(write, pipe_no_reader_sets_EPIPE_without_crashing) {
    int fds[2];
    cr_assert_eq(pipe(fds), 0);
    int r = fds[0], w = fds[1];

    // Ignore SIGPIPE so write returns EPIPE instead of raising.
    void (*old)(int) = signal(SIGPIPE, SIG_IGN);
    close(r);

    const char msg[] = "hello";
    result_ssize_t n = probe_libc_write(w, msg, sizeof(msg));
    cr_expect_eq(n.error, EPIPE, "Expected EPIPE, got %d (%s)", n.error, strerror(n.error));

    close(w);
    signal(SIGPIPE, old);
}

// Non-blocking pipe full -> EAGAIN
Test(write, nonblocking_pipe_full_sets_EAGAIN) {
    int fds[2];
    cr_assert_eq(pipe(fds), 0);
    int r = fds[0], w = fds[1];

    // Make write end non-blocking
    int flags = fcntl(w, F_GETFL);
    cr_assert_neq(flags, -1);
    cr_assert_eq(fcntl(w, F_SETFL, flags | O_NONBLOCK), 0);

    fill_pipe_to_eagain(w);

    const char msg[] = "x";
    result_ssize_t n = probe_libc_write(w, msg, sizeof(msg));
    cr_expect_eq(n.error, EAGAIN, "Expected EAGAIN on full non-blocking pipe, got %d (%s)",
                 n.error, strerror(n.error));

    close(r);
    close(w);
}

// Large-ish write to a regular file (tests that the function can handle buffers > PIPE_BUF).
Test(write, large_buffer_regular_file) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    const size_t N = 128 * 1024; // 128 KiB
    char *buf = malloc(N);
    cr_assert_not_null(buf);

    // Fill with a pattern
    for (size_t i = 0; i < N; ++i) buf[i] = (char)(i & 0xFF);

    result_ssize_t n = probe_libc_write(fd, buf, N);
    cr_assert_eq(n.error, 0, "probe_libc_write errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, (ssize_t)N, "Expected to write %zu bytes, wrote %zd", N, n.value);

    // Spot-check a few locations by reading back a smaller sample
    if (lseek(fd, 0, SEEK_SET) != (off_t)-1) {
        char chk[256];
        ssize_t r = read(fd, chk, sizeof(chk));
        cr_expect_eq(r, (ssize_t)sizeof(chk));
        for (size_t i = 0; i < (size_t)r; ++i) {
            cr_expect_eq((unsigned char)chk[i], (unsigned char)(i & 0xFF), "Mismatch at %zu", i);
        }
    }

    free(buf);
    close(fd);
}



// Basic success case: read all bytes from a regular file
Test(read, reads_all_bytes_from_regular_file) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    const char msg[] = "hello\n";
    write_all(fd, msg, sizeof(msg));

    char buf[64] = {0};
    result_ssize_t n = probe_libc_read(fd, buf, sizeof(buf));
    cr_assert_eq(n.error, 0, "probe_libc_read errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, (ssize_t)sizeof(msg));
    cr_expect_arr_eq(buf, msg, sizeof(msg));

    close(fd);
}

// EOF: should return 0
Test(read, eof_returns_zero) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);
    // empty file

    char buf[16];
    result_ssize_t n = probe_libc_read(fd, buf, sizeof(buf));
    cr_assert_eq(n.error, 0, "probe_libc_read errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, 0, "Expected 0 at EOF, got %zd", n.value);

    close(fd);
}

// Zero-length read: should return 0 and not touch buffer
Test(read, zero_length_read_returns_zero_and_noop) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    char buf[8];
    memset(buf, 0xAA, sizeof(buf));

    result_ssize_t n = probe_libc_read(fd, buf, 0);
    cr_assert_eq(n.error, 0, "probe_libc_read errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, 0);
    for (size_t i = 0; i < sizeof(buf); i++)
        cr_expect_eq(buf[i], (char)0xAA, "Buffer modified on zero-length read at index %zu", i);

    close(fd);
}

// Invalid fd
Test(read, invalid_negative_fd_sets_EBADF) {
    char buf[4];
    result_ssize_t n = probe_libc_read(-1, buf, sizeof(buf));
    cr_expect_eq(n.error, EBADF, "Expected EBADF, got %d (%s)", n.error, strerror(n.error));
}

// Closed fd
Test(read, closed_fd_sets_EBADF) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);
    close(fd);

    char buf[4];
    result_ssize_t n = probe_libc_read(fd, buf, sizeof(buf));
    cr_expect_eq(n.error, EBADF, "Expected EBADF, got %d (%s)", n.error, strerror(n.error));

}

// Write-only fd
Test(read, write_only_fd_sets_EBADF) {
    char path[128] = {0};
    int wfd = mktemp_file(path, sizeof(path));
    cr_assert_neq(wfd, -1);
    close(wfd);

    int fd = open(path, O_WRONLY);
    cr_assert_neq(fd, -1);
    unlink(path);

    char buf[4];
    result_ssize_t n = probe_libc_read(fd, buf, sizeof(buf));
    cr_expect_eq(n.error, EBADF, "Expected EBADF, got %d (%s)", n.error, strerror(n.error));

    close(fd);
}

// NULL buffer
Test(read, null_buffer_nonzero_count_sets_EFAULT) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    // Ensure file has at least 1 byte so that the EFAULT condition doesn't get optimized out
    const char msg[] = "x";
    write_all(fd, msg, sizeof(msg));

    result_ssize_t n = probe_libc_read(fd, NULL, 1);
    cr_expect_eq(n.error, EFAULT, "Expected EFAULT, got %d (%s)", n.error, strerror(n.error));

    close(fd);
}

// Pipe with no writer: returns 0 (EOF)
Test(read, pipe_no_writer_returns_zero) {
    int fds[2];
    cr_assert_eq(pipe(fds), 0);
    int r = fds[0], w = fds[1];

    close(w);

    char buf[8];
    result_ssize_t n = probe_libc_read(r, buf, sizeof(buf));
    cr_assert_eq(n.error, 0, "probe_libc_read errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, 0, "Expected EOF=0, got %zd", n.value);

    close(r);
}

// Non-blocking empty pipe: should return EAGAIN
Test(read, nonblocking_empty_pipe_sets_EAGAIN) {
    int fds[2];
    cr_assert_eq(pipe(fds), 0);
    int r = fds[0], w = fds[1];
    (void)w;

    int flags = fcntl(r, F_GETFL);
    cr_assert_neq(flags, -1);
    cr_assert_eq(fcntl(r, F_SETFL, flags | O_NONBLOCK), 0);

    char buf[8];
    result_ssize_t n = probe_libc_read(r, buf, sizeof(buf));
    cr_expect_eq(n.error, EAGAIN, "Expected EAGAIN on empty non-blocking pipe, got %d (%s)",
                 n.error, strerror(n.error));

    close(r);
    close(w);
}

// Partial read: file smaller than requested
Test(read, partial_read_returns_less_than_count) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    const char msg[] = "hi";
    write_all(fd, msg, sizeof(msg));

    char buf[16] = {0};
    result_ssize_t n = probe_libc_read(fd, buf, sizeof(buf));
    cr_assert_eq(n.error, 0, "probe_libc_read errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, (ssize_t)sizeof(msg), "Expected %zd, got %zd", (ssize_t)sizeof(msg),
                 n.value);
    cr_expect_arr_eq(buf, msg, sizeof(msg));

    close(fd);
}

// Large buffer read
Test(read, large_buffer_regular_file) {
    char path[128] = {0};
    int fd = mktemp_file(path, sizeof(path));
    cr_assert_neq(fd, -1);
    unlink(path);

    const size_t N = 128 * 1024; // 128 KiB
    char *src = malloc(N);
    cr_assert_not_null(src);
    for (size_t i = 0; i < N; i++) src[i] = (char)(i & 0xFF);
    write_all(fd, src, N);

    char *dst = malloc(N);
    cr_assert_not_null(dst);

    result_ssize_t n = probe_libc_read(fd, dst, N);
    cr_assert_eq(n.error, 0, "probe_libc_read errored with: %s (%d)", strerror(n.error), n.error);
    cr_assert_eq(n.value, (ssize_t)N, "Expected to read %zu, got %zd", N, n.value);

    for (size_t i = 0; i < 256; i++) {
        cr_expect_eq((unsigned char)dst[i], (unsigned char)(i & 0xFF), "Mismatch at %zu", i);
    }

    free(src);
    free(dst);
    close(fd);
}



// Basic success: copy small file fully
Test(sendfile, copy_small_file_success) {
    char src_path[128], dst_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    int out_fd = mktemp_file(dst_path, sizeof(dst_path));
    cr_assert_neq(in_fd, -1);
    cr_assert_neq(out_fd, -1);
    unlink(src_path);
    unlink(dst_path);

    const char msg[] = "hello world\n";
    write_all(in_fd, msg, sizeof(msg));

    result_ssize_t n = probe_libc_sendfile(out_fd, in_fd, NULL, sizeof(msg));
    cr_assert_eq(n.error, 0, "probe_libc_sendfile errored with: %s (%d)", strerror(n.error),
                 n.error);
    cr_assert_eq(n.value, (ssize_t)sizeof(msg), "Expected to send %zd, actually sent %zd",
                 (ssize_t)sizeof(msg), n.value);

    char buf[64] = {0};
    size_t got = read_all(out_fd, buf, sizeof(buf));
    cr_expect_eq(got, sizeof(msg));
    cr_expect_arr_eq(buf, msg, sizeof(msg));

    close(in_fd);
    close(out_fd);
}

// Zero count: should return 0
Test(sendfile, zero_count_returns_zero) {
    char src_path[128], dst_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    int out_fd = mktemp_file(dst_path, sizeof(dst_path));
    cr_assert_neq(in_fd, -1);
    cr_assert_neq(out_fd, -1);
    unlink(src_path);
    unlink(dst_path);

    const char msg[] = "x";
    write_all(in_fd, msg, sizeof(msg));

    result_ssize_t n = probe_libc_sendfile(out_fd, in_fd, NULL, 0);
    cr_assert_eq(n.error, 0, "probe_libc_sendfile errored with: %s (%d)", strerror(n.error),
                 n.error);
    cr_assert_eq(n.value, 0, "Unexpectedly sent %zd", n.value);

    close(in_fd);
    close(out_fd);
}

// Partial copy when count > file size
Test(sendfile, partial_copy_when_count_exceeds_file) {
    char src_path[128], dst_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    int out_fd = mktemp_file(dst_path, sizeof(dst_path));
    cr_assert_neq(in_fd, -1);
    cr_assert_neq(out_fd, -1);
    unlink(src_path);
    unlink(dst_path);

    const char msg[] = "abc";
    write_all(in_fd, msg, sizeof(msg));

    result_ssize_t n = probe_libc_sendfile(out_fd, in_fd, NULL, 1000);
    cr_assert_eq(n.error, 0, "probe_libc_sendfile errored with: %s (%d)", strerror(n.error),
                 n.error);
    cr_assert_eq(n.value, (ssize_t)sizeof(msg), "Expected to send %zd, actually sent %zd",
                 (ssize_t)sizeof(msg), n.value);

    char buf[16] = {0};
    size_t got = read_all(out_fd, buf, sizeof(buf));
    cr_expect_eq(got, sizeof(msg));
    cr_expect_arr_eq(buf, msg, sizeof(msg));

    close(in_fd);
    close(out_fd);
}

// With offset: should not advance in_fd’s file pointer
Test(sendfile, with_offset_does_not_advance_file_position) {
    char src_path[128], dst_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    int out_fd = mktemp_file(dst_path, sizeof(dst_path));
    cr_assert_neq(in_fd, -1);
    cr_assert_neq(out_fd, -1);
    unlink(src_path);
    unlink(dst_path);

    const char msg[] = "abcdef";
    write_all(in_fd, msg, sizeof(msg));

    off_t off = 2;
    result_ssize_t n = probe_libc_sendfile(out_fd, in_fd, &off, 3);
    cr_assert_eq(n.error, 0, "probe_libc_sendfile errored with: %s (%d)", strerror(n.error),
                 n.error);
    cr_assert_eq(n.value, 3, "Expected to send 3, actually sent %zd", n.value);

    // Verify copied substring
    char buf[16] = {0};
    size_t got = read_all(out_fd, buf, sizeof(buf));
    cr_expect_eq(got, 3);
    cr_expect_eq(buf[0], 'c');
    cr_expect_eq(buf[1], 'd');
    cr_expect_eq(buf[2], 'e');

    // Verify original file offset unchanged (still at start)
    off_t cur = lseek(in_fd, 0, SEEK_CUR);
    cr_assert_eq(cur, 0, "Expected file offset to be unchanged");

    close(in_fd);
    close(out_fd);
}

// Invalid in_fd
Test(sendfile, invalid_in_fd_sets_EBADF) {
    char dst_path[128];
    int out_fd = mktemp_file(dst_path, sizeof(dst_path));
    cr_assert_neq(out_fd, -1);
    unlink(dst_path);

    result_ssize_t n = probe_libc_sendfile(out_fd, -1, NULL, 10);
    cr_assert_eq(n.error, EBADF, "Expected EBADF, got %d (%s)", n.error, strerror(n.error));

    close(out_fd);
}

// Invalid out_fd
Test(sendfile, invalid_out_fd_sets_EBADF) {
    char src_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    cr_assert_neq(in_fd, -1);
    unlink(src_path);

    const char msg[] = "data";
    write_all(in_fd, msg, sizeof(msg));

    result_ssize_t n = probe_libc_sendfile(-1, in_fd, NULL, sizeof(msg));
    cr_assert_eq(n.error, EBADF, "Expected EBADF, got %d (%s)", n.error, strerror(n.error));

    close(in_fd);
}

// Out fd not writable
Test(sendfile, out_fd_not_writable_sets_EBADF) {
    char src_path[128], dst_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    int wfd = mktemp_file(dst_path, sizeof(dst_path));
    close(wfd);

    int out_fd = open(dst_path, O_RDONLY);
    cr_assert_neq(out_fd, -1);
    unlink(src_path);
    unlink(dst_path);

    const char msg[] = "test";
    write_all(in_fd, msg, sizeof(msg));

    result_ssize_t n = probe_libc_sendfile(out_fd, in_fd, NULL, sizeof(msg));
    cr_assert_eq(n.error, EBADF, "Expected EBADF, got %d (%s)", n.error, strerror(n.error));

    close(in_fd);
    close(out_fd);
}

// In fd not a regular file (pipe) should fail with EINVAL
Test(sendfile, in_fd_not_regular_file_sets_EINVAL) {
    int fds[2];
    cr_assert_eq(pipe(fds), 0);
    int r = fds[0], w = fds[1];

    char dst_path[128];
    int out_fd = mktemp_file(dst_path, sizeof(dst_path));
    cr_assert_neq(out_fd, -1);
    unlink(dst_path);

    result_ssize_t n = probe_libc_sendfile(out_fd, r, NULL, 10);
    cr_assert_eq(n.error, EINVAL, "Expected EINVAL, got %d (%s)", n.error, strerror(n.error));

    close(r);
    close(w);
    close(out_fd);
}

// Invalid offset pointer (non-mapped memory) → EFAULT
Test(sendfile, invalid_offset_pointer_sets_EFAULT) {
    char src_path[128], dst_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    int out_fd = mktemp_file(dst_path, sizeof(dst_path));
    cr_assert_neq(in_fd, -1);
    cr_assert_neq(out_fd, -1);
    unlink(src_path);
    unlink(dst_path);

    const char msg[] = "hello";
    write_all(in_fd, msg, sizeof(msg));

    off_t *bad_ptr = (off_t *)0x1; // invalid address
    result_ssize_t n = probe_libc_sendfile(out_fd, in_fd, bad_ptr, sizeof(msg));
    cr_assert_eq(n.error, EFAULT, "Expected EFAULT, got %d (%s)", n.error, strerror(n.error));

    close(in_fd);
    close(out_fd);
}

// Large copy
Test(sendfile, large_copy_success) {
    char src_path[128], dst_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    int out_fd = mktemp_file(dst_path, sizeof(dst_path));
    cr_assert_neq(in_fd, -1);
    cr_assert_neq(out_fd, -1);
    unlink(src_path);
    unlink(dst_path);

    const size_t N = 128 * 1024;
    char *buf = malloc(N);
    cr_assert_not_null(buf);
    for (size_t i = 0; i < N; i++) buf[i] = (char)(i & 0xFF);
    write_all(in_fd, buf, N);

    result_ssize_t n = probe_libc_sendfile(out_fd, in_fd, NULL, N);
    cr_assert_eq(n.error, 0, "probe_libc_sendfile errored with: %s (%d)", strerror(n.error),
                 n.error);
    cr_assert_eq(n.value, (ssize_t)N, "Expected to send %zd, actually sent %zd", (ssize_t)N,
                 n.value);

    char check[256];
    size_t got = read_all(out_fd, check, sizeof(check));
    for (size_t i = 0; i < got; i++) {
        cr_expect_eq((unsigned char)check[i], (unsigned char)(i & 0xFF));
    }

    free(buf);
    close(in_fd);
    close(out_fd);
}

// Out fd is a socketpair: Linux only feature
Test(sendfile, out_fd_socketpair_success) {
#ifdef __linux__
    int sv[2];
    cr_assert_eq(socketpair(AF_UNIX, SOCK_STREAM, 0, sv), 0);
    int sock_r = sv[0], sock_w = sv[1];

    char src_path[128];
    int in_fd = mktemp_file(src_path, sizeof(src_path));
    cr_assert_neq(in_fd, -1);
    unlink(src_path);

    const char msg[] = "socket sendfile\n";
    write_all(in_fd, msg, sizeof(msg));

    result_ssize_t n = probe_libc_sendfile(sock_w, in_fd, NULL, sizeof(msg));
    cr_assert_eq(n.error, 0, "probe_libc_sendfile errored with: %s (%d)", strerror(n.error),
                 n.error);
    cr_assert_eq(n.value, (ssize_t)sizeof(msg), "Expected to send %zd, actually sent %zd",
                 (ssize_t)sizeof(msg), n.value);

    // Read back from the socket peer
    char buf[64] = {0};
    ssize_t r = read(sock_r, buf, sizeof(buf));
    cr_expect_eq(r, (ssize_t)sizeof(msg));
    cr_expect_arr_eq(buf, msg, sizeof(msg));

    close(in_fd);
    close(sock_r);
    close(sock_w);
#else
    cr_skip("sendfile to socketpair only supported on Linux");
#endif
}
