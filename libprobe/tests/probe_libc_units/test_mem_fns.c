
// this exists solely for lsp and will get preprocessed out during build time
#ifndef SRC_INCLUDED
#include <criterion/criterion.h>
#include "probe_libc.h"
#endif

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

Test(memcmp, ne_fuzzing) {
    srand(69420);

    for (int i = 0; i < 10000; ++i) {
        int buf1[32];
        int buf2[32];
        for (int j = 0; j < 32; ++j) {
            buf1[j] = rand();
            buf2[j] = rand();
        }

        int refrence = memcmp(buf1, buf2, 32);

        if (refrence > 0) {
            cr_assert(
                probe_libc_memcmp(buf1, buf2, 32) > 0,
                "memcmp() > 0, probe_libc_memcmp() <= 0"
            );
        } else if (refrence < 0) {
            cr_assert(
                probe_libc_memcmp(buf1, buf2, 32) < 0,
                "memcmp() < 0, probe_libc_memcmp() >= 0"
            );
        } else {
            cr_assert(
                probe_libc_memcmp(buf1, buf2, 32) == 0,
                "memcmp() == 0, probe_libc_memcmp() != 0"
            );
        }
    }
}

Test(memcmp, eq_fuzzing) {
    srand(69420);

    for (int i = 0; i < 10000; ++i) {
        int size = rand() % 4096;
        int* buf1 = malloc(size * sizeof(int));
        int* buf2 = malloc(size * sizeof(int));
        for (int j = 0; j < size; ++j) {
            int x = rand();
            buf1[j] = x;
            buf2[j] = x;
        }

        int refrence = memcmp(buf1, buf2, size * sizeof(int));
        if (refrence > 0) {
            cr_assert(
                probe_libc_memcmp(buf1, buf2, size * sizeof(int)) > 0,
                "memcmp() > 0, probe_libc_memcmp() <= 0"
            );
        } else if (refrence < 0) {
            cr_assert(
                probe_libc_memcmp(buf1, buf2, size * sizeof(int)) < 0,
                "memcmp() < 0, probe_libc_memcmp() >= 0"
            );
        } else {
            cr_assert(
                probe_libc_memcmp(buf1, buf2, size * sizeof(int)) == 0,
                "memcmp() == 0, probe_libc_memcmp() != 0"
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

Test(memcpy, fuzzing) {
    srand(69420);

    for (int i = 0; i < 10000; ++i) {
        int size = rand() % 4096;
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
