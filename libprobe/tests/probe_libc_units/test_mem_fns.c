
// this exists solely for lsp and will get preprocessed out during build time
#ifndef SRC_INCLUDED
#include <criterion/criterion.h>
#include "probe_libc.h"
#endif

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

Test(memcmp, eq_aligned) {
    cr_assert(
        probe_libc_memcmp("testtest", "testtest", 8) == 0,
        "Expected identical aligned strigns to be equal"
    );
}

Test(memcmp, eq_unaligned) {
    cr_assert(
        probe_libc_memcmp("testtest123", "testtest123", 11) == 0,
        "Expected identical unaligned strings to be equal"
    );
}

Test(memcmp, eq_prefix) {
    cr_assert(
        probe_libc_memcmp("test123", "test456", 4) == 0,
        "Expected first 4 bytes of strings to be equal"
    );
}

Test(memcmp, neq_prefix) {
    cr_assert(
        probe_libc_memcmp("test123", "test456", 6) != 0,
        "Expected difference at index 4"
    );
}

Test(memcmp, lt_aligned) {
    cr_assert(
        probe_libc_memcmp("1111222233334444", "1111222244443333", 16) < 0,
        "Expected chars '3' < '4' at index 8"
    );
}

Test(memcmp, gt_aligned) {
    cr_assert(
        probe_libc_memcmp("1111222244443333", "1111222233334444", 16) > 0,
        "Expected chars '4' < '3' at index 8"
    );
}

Test(memcmp, lt_unaligned) {
    cr_assert(
        probe_libc_memcmp("11112222333", "11112222334", 11) < 0,
        "Expected chars '3' < '4' at index 11"
    );
}

Test(memcmp, gt_unaligned) {
    cr_assert(
        probe_libc_memcmp("11112222334", "11112222333", 11) > 0,
        "Expected chars '4' < '3' at index 11"
    );
}

Test(memcmp, zero_valid) {
    cr_assert(
        probe_libc_memcmp("111", "222", 0) == 0,
        "Expected length 0 comparison to always succeed"
    );
}

Test(memcmp, zero_memcmp) {
    cr_assert(
        probe_libc_memcmp("abc", "def", 0) == 0,
        "Expected length 0 comparison to always succeed"
    );
}

Test(memcmp, ne_fuzzing) {
    srand(FUZZING_SEED);

    for (size_t i = 0; i < FUZZING_COUNT; ++i) {
        int buf1[32];
        int buf2[32];
        for (int j = 0; j < 32; ++j) {
            buf1[j] = rand();
            buf2[j] = rand();
        }

        int expected = memcmp(buf1, buf2, 32);
        int actual = probe_libc_memcmp(buf1, buf2, 32);

        if (expected > 0) {
            cr_assert(
                actual > 0,
                "memcmp() returned %d but probe_libc_memcmp() returned %d",
                expected,
                actual
            );
        } else if (expected < 0) {
            cr_assert(
                actual < 0,
                "memcmp() returned %d but probe_libc_memcmp() returned %d",
                expected,
                actual
            );
        } else {
            cr_assert(
                actual == 0,
                "memcmp() returned %d but probe_libc_memcmp() returned %d",
                expected,
                actual
            );
        }
    }
}

Test(memcmp, eq_fuzzing) {
    srand(FUZZING_SEED);

    for (size_t i = 0; i < FUZZING_COUNT; ++i) {
        int size = rand() % 0x1000;
        int* buf1 = malloc(size * sizeof(int));
        int* buf2 = malloc(size * sizeof(int));
        for (int j = 0; j < size; ++j) {
            int x = rand();
            buf1[j] = x;
            buf2[j] = x;
        }

        int expected = memcmp(buf1, buf2, size * sizeof(int));
        int actual = probe_libc_memcmp(buf1, buf2, size * sizeof(int));

        if (expected > 0) {
            cr_assert(
                actual > 0,
                "memcmp() returned %d but probe_libc_memcmp() returned %d",
                expected,
                actual
            );
        } else if (expected < 0) {
            cr_assert(
                actual < 0,
                "memcmp() returned %d but probe_libc_memcmp() returned %d",
                expected,
                actual
            );
        } else {
            cr_assert(
                actual == 0,
                "memcmp() returned %d but probe_libc_memcmp() returned %d",
                expected,
                actual
            );
        }

        free(buf1);
        free(buf2);
    }
}



Test(memcpy, aligned) {
    char* orig = "test1234**##@@!!";
    char new[16];

    probe_libc_memcpy(new, orig, 16);
    cr_assert(memcmp(new, orig, 16) == 0, "Aligned memcpy failed");
}

Test(memcpy, unaligned) {
    char* orig = "test1234**##@@!!456";
    char new[19];

    probe_libc_memcpy(new, orig, 19);
    cr_assert(memcmp(new, orig, 19) == 0, "Unaligned memcpy failed");
}

Test(memcpy, zero_valid) {
    char* orig = "test1234";
    char new[8] = {0};

    probe_libc_memcpy(new, orig, 0);
    for (int i = 0; i < 8; ++i) {
        cr_assert(new[i] == 0, "byte at index %d set to %d (not 0)", i, new[i]);
    }
}

Test(memcpy, fuzzing) {
    srand(FUZZING_SEED);

    for (size_t i = 0; i < FUZZING_COUNT; ++i) {
        int size = rand() % 0x1000;
        int* buf1 = malloc(size * sizeof(int));
        int* buf2 = malloc(size * sizeof(int));
        for (int j = 0; j < size; ++j) {
            int x = rand();
            buf1[j] = x;
        }

        probe_libc_memcpy(buf2, buf1, size * sizeof(int));
        cr_assert(memcmp(buf2, buf1, size * sizeof(int)) == 0, "Fuzzing memcpy failed");

        free(buf1);
        free(buf2);
    }
}



Test(memset, aligned) {
    char buf[32] = {0};

    probe_libc_memset(buf, 'A', 32);
    for (int i = 0; i < 32; ++i) {
        cr_assert(buf[i] == 'A', "Expected set byte at index %d", i);
    }
}

Test(memset, unaligned) {
    char buf[43] = {0};

    probe_libc_memset(buf, 'A', 43);
    for (int i = 0; i < 43; ++i) {
        cr_assert(buf[i] == 'A', "Expected set byte at index %d", i);
    }
}

Test(memset, zero_valid) {
    char buf[8] = {0};

    probe_libc_memset(buf, 'B', 0);
    for (int i = 0; i < 8; ++i) {
        cr_assert(buf[i] == 0, "Byte at index %d set to %d (not 0)", i, buf[i]);
    }
}

Test(memset, zeros) {
    for (int i = 0; i < 256; ++i) {
        char* buf = malloc(i);
        probe_libc_memset(buf, 0, i);
        for (int j = 0; j < i; ++j) {
            cr_assert(buf[j] == 0, "Expected zero byte at %d of buffer length %d", j, i);
        }
        free(buf);
    }
}

Test(memset, fuzzing) {
    srand(FUZZING_SEED);

    for (size_t i = 0; i < FUZZING_COUNT; ++i) {
        int x = rand() % 256;
        int size = rand() % 0x1000;
        char* buf_expected = malloc(size);
        char* buf_actual = malloc(size);

        memset(buf_expected, x, size);
        probe_libc_memset(buf_actual, x, size);

        cr_assert(memcmp(buf_expected, buf_actual, size) == 0, "Expected same result buffer");
    }
}

Test(memcount, stops_after_len) {
    cr_assert_eq(probe_libc_memcount("aa34a", 4, 'a'), 2);
}
