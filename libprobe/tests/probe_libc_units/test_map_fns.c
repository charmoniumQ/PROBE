
// this exists solely for lsp and will get preprocessed out during build time
#ifndef SRC_INCLUDED
#include <criterion/criterion.h>
#include "probe_libc.h"
#endif

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define PAGE_SIZE sysconf(_SC_PAGESIZE)

// basic success case
Test(mmap, anonymous_rw_basic) {
    result_mem res = probe_libc_mmap(NULL, PAGE_SIZE, PROT_READ | PROT_WRITE,
                                     MAP_PRIVATE | MAP_ANONYMOUS, -1);
    cr_assert_eq(res.error, 0, "Expected success but got error=%d", res.error);
    cr_assert_neq(res.value, MAP_FAILED, "Expected valid mapping");
    strcpy((char *)res.value, "hello mmap");
    cr_assert_str_eq((char *)res.value, "hello mmap");

    munmap(res.value, PAGE_SIZE);
}

// zero length
Test(mmap, zero_length_should_fail) {
    result_mem res = probe_libc_mmap(NULL, 0, PROT_READ,
                                     MAP_PRIVATE | MAP_ANONYMOUS, -1);
    cr_assert_eq(res.error, EINVAL, "Expected EINVAL for zero-length mapping, but got %d (%s)",
                 res.error, strerror(res.error));
}

// invalid fd without MAP_ANONYMOUS
Test(mmap, invalid_fd_no_anonymous) {
    result_mem res = probe_libc_mmap(NULL, PAGE_SIZE, PROT_READ,
                                     MAP_PRIVATE, -1);
    cr_assert_eq(res.error, EBADF,
                 "Expected EBADF for invalid fd without MAP_ANONYMOUS, but got %d (%s)", res.error,
                 strerror(res.error));
}

// valid file backed
Test(mmap, file_backed_mapping) {
    int fd = open("/dev/zero", O_RDWR);
    cr_assert_neq(fd, -1, "Failed to open /dev/zero");

    result_mem res = probe_libc_mmap(NULL, PAGE_SIZE, PROT_READ | PROT_WRITE,
                                     MAP_SHARED, fd);
    close(fd);
    cr_assert_eq(res.error, 0, "Expected success mapping /dev/zero but got %d", res.error);
    cr_assert_neq(res.value, MAP_FAILED, "Expected valid mapping");

    strcpy((char *)res.value, "file mmap");
    cr_assert_str_eq((char *)res.value, "file mmap");

    munmap(res.value, PAGE_SIZE);
}

// MAP_FIXED with invalid addr
Test(mmap, invalid_fixed_addr) {
    void *bad_addr = (void *)0x12345; // not page aligned
    result_mem res = probe_libc_mmap(bad_addr, PAGE_SIZE,
                                     PROT_READ | PROT_WRITE,
                                     MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED,
                                     -1);
    cr_assert_eq(res.error, EINVAL,
                 "Expected EINVAL with MAP_FIXED unaligned address, but got %d (%s)", res.error,
                 strerror(res.error));
}

// PROT_NONE access check (should segfault if touched)
Test(mmap, prot_none_access_fails, .signal = SIGSEGV) {
    result_mem res = probe_libc_mmap(NULL, PAGE_SIZE, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1);
    cr_assert_eq(res.error, 0, "Expected success creating PROT_NONE map");
    cr_assert_neq(res.value, MAP_FAILED, "Expected valid mapping");

    // Trigger segfault
    volatile char c = *((char *)res.value);
    (void)c;
}

// large length (should fail)
Test(mmap, too_large_length) {
    size_t big = (size_t)-1 & ~(PAGE_SIZE - 1); // huge rounded size
    result_mem res = probe_libc_mmap(NULL, big, PROT_READ, MAP_PRIVATE | MAP_ANONYMOUS, -1);
    cr_assert_eq(res.error, ENOMEM, "Expected ENOMEM for huge mapping, but got %d (%s)", res.error,
                 strerror(res.error));
}



// basic success
Test(munmap, basic_success) {
    void *ptr = mmap(NULL, PAGE_SIZE, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    cr_assert_neq(ptr, MAP_FAILED, "mmap failed unexpectedly");

    result r = probe_libc_munmap(ptr, PAGE_SIZE);
    cr_assert_eq(r, 0, "Expected success from munmap but got %d", r);
}

// zero length
Test(munmap, zero_length_should_fail) {
    void *ptr = mmap(NULL, PAGE_SIZE, PROT_READ,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    cr_assert_neq(ptr, MAP_FAILED);

    result r = probe_libc_munmap(ptr, 0);
    cr_assert_eq(r, EINVAL, "Expected EINVAL for length=0 but got %d", r);

    // cleanup validly
    probe_libc_munmap(ptr, PAGE_SIZE);
}

// unaligned address
Test(munmap, unaligned_address_should_fail) {
    void *ptr = mmap(NULL, PAGE_SIZE * 2, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    cr_assert_neq(ptr, MAP_FAILED);

    char *addr = (char *)ptr;
    result r = probe_libc_munmap(addr + 1, PAGE_SIZE);
    cr_assert_eq(r, EINVAL, "Expected EINVAL for unaligned address but got %d", r);

    // cleanup
    probe_libc_munmap(ptr, PAGE_SIZE * 2);
}

// partial unmap
Test(munmap, partial_unmap_should_succeed) {
    void *ptr = mmap(NULL, PAGE_SIZE * 2, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    cr_assert_neq(ptr, MAP_FAILED);

    char *addr = (char *)ptr;
    result r = probe_libc_munmap(addr + PAGE_SIZE, PAGE_SIZE);
    cr_assert_eq(r, 0, "Partial unmap 1 should succeed but got %d", r);

    r = probe_libc_munmap(addr, PAGE_SIZE);
    cr_assert_eq(r, 0, "Partial unmap 2 should succeed but got %d", r);
}

// too large length
Test(munmap, too_large_length_should_fail) {
    void *ptr = mmap(NULL, PAGE_SIZE, PROT_READ,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    cr_assert_neq(ptr, MAP_FAILED);

    result r = probe_libc_munmap(ptr, SIZE_MAX & ~(PAGE_SIZE - 1));
    cr_assert_eq(r, EINVAL, "Expected EINVAL for huge mapping but got %d", r);

    munmap(ptr, PAGE_SIZE);
}
