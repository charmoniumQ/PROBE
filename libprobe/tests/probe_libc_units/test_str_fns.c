
// this exists solely for lsp and will get preprocessed out during build time
#ifndef SRC_INCLUDED
#include <criterion/criterion.h>
#include "probe_libc.h"
#endif

#include <stddef.h>
#include <string.h>

Test(strnlen, empty_string) {
    const char *str = "";
    size_t result = probe_libc_strnlen(str, 10);
    cr_assert(result == 0, "Expected 0, got %zu for empty string with maxlen=10", result);
}

Test(strnlen, maxlen_zero) {
    const char *str = "hello";
    size_t result = probe_libc_strnlen(str, 0);
    cr_assert(result == 0, "Expected 0, got %zu for non-empty string with maxlen=0", result);
}

Test(strnlen, short_string_less_than_maxlen) {
    const char *str = "hi";
    size_t result = probe_libc_strnlen(str, 10);
    cr_assert(result == 2, "Expected 2, got %zu for string 'hi' with maxlen=10", result);
}

Test(strnlen, string_equal_to_maxlen) {
    const char *str = "hello";
    size_t result = probe_libc_strnlen(str, 5);
    cr_assert(result == 5, "Expected 5, got %zu for string 'hello' with maxlen=5", result);
}

Test(strnlen, string_longer_than_maxlen) {
    const char *str = "hello world";
    size_t result = probe_libc_strnlen(str, 5);
    cr_assert(result == 5, "Expected 5, got %zu for string 'hello world' with maxlen=5", result);
}

Test(strnlen, null_terminator_at_maxlen) {
    const char str[] = { 'a', 'b', 'c', 'd', '\0', 'x', 'y' };
    size_t result = probe_libc_strnlen(str, 5);
    cr_assert(result == 4, "Expected 4, got %zu for string with null at position 4 and maxlen=5", result);
}

Test(strnlen, embedded_null_before_maxlen) {
    const char str[] = { 'a', 'b', '\0', 'c', 'd' };
    size_t result = probe_libc_strnlen(str, 5);
    cr_assert(result == 2, "Expected 2, got %zu for string with embedded null at position 2", result);
}

Test(strnlen, embedded_null_at_maxlen_minus_1) {
    const char str[] = { 'a', 'b', 'c', '\0', 'd' };
    size_t result = probe_libc_strnlen(str, 4);
    cr_assert(result == 3, "Expected 3, got %zu for string with null at position 3 and maxlen=4", result);
}

Test(strnlen, large_maxlen_on_small_string) {
    const char *str = "short";
    size_t result = probe_libc_strnlen(str, 1000);
    cr_assert(result == 5, "Expected 5, got %zu for string 'short' with large maxlen=1000", result);
}

Test(strnlen, one_char_string_maxlen_1) {
    const char *str = "a";
    size_t result = probe_libc_strnlen(str, 1);
    cr_assert(result == 1, "Expected 1, got %zu for string 'a' with maxlen=1", result);
}

Test(strnlen, null_pointer_maxlen_zero) {
    const char *str = NULL;
    size_t result = probe_libc_strnlen(str, 0);
    cr_assert(result == 0, "Expected 0, got %zu for NULL pointer with maxlen=0", result);
}

Test(strnlen, null_pointer_nonzero_maxlen) {
    const char *str = NULL;
    size_t result = probe_libc_strnlen(str, 5);
    cr_assert(result == 0, "Expected 0, got %zu for NULL pointer with maxlen=5", result);
}

Test(strnlen, fuzzing) {
    srand(FUZZING_SEED);

    for (int i = 0; i < 10000; ++i) {
        char buf[4096];
        memset(buf, (rand() % 255) + 1, rand() % 4096);
        int n = rand() % 4096;

        size_t expected = strnlen(buf, n);
        size_t actual = probe_libc_strnlen(buf, n);

        cr_assert(expected == actual, "Expected %zu, got %zu", expected, actual);
    }
}



// Helper function to compare with standard strncpy behavior
static inline void assert_strncpy_equal(const char *src, size_t n) {
    char expected[100] = {0};
    char actual[100] = {0};

    strncpy(expected, src, n);
    probe_libc_strncpy(actual, src, n);

    cr_assert_arr_eq(actual, expected, n, 
        "Expected strncpy result: \"%.*s\", but got: \"%.*s\"",
        (int)n, expected, (int)n, actual);
}

// Basic copy
Test(strncpy, basic_copy) {
    assert_strncpy_equal("hello", 5);
}

// Copy with n larger than src length
Test(strncpy, copy_with_padding) {
    assert_strncpy_equal("hi", 10);
}

// Copy with n == 0
Test(strncpy, zero_length_copy) {
    assert_strncpy_equal("hello", 0);
}

// Source is empty string
Test(strncpy, empty_source) {
    assert_strncpy_equal("", 5);
}

// Source longer than n (truncation)
Test(strncpy, source_truncation) {
    assert_strncpy_equal("this is a long string", 4);
}

// Copy exactly strlen(src)
Test(strncpy, exact_length_copy) {
    assert_strncpy_equal("abcdef", 6);
}

// Verify return value is dest
Test(strncpy, return_value_check) {
    char dest[100] = {0};
    char *ret = probe_libc_strncpy(dest, "hello", 5);
    cr_assert_eq(ret, dest, "Function should return the destination pointer");
}

// Ensure null characters are copied
Test(strncpy, internal_nulls) {
    const char src[] = {'a', '\0', 'b', 'c', '\0'};
    char expected[10] = {0};
    char actual[10] = {0};

    strncpy(expected, src, 5);
    probe_libc_strncpy(actual, src, 5);

    cr_assert_arr_eq(actual, expected, 5, "Expected: \"%.*s\", Got: \"%.*s\"",
        5, expected, 5, actual);
}

Test(strncpy, fuzzing) {
    srand(FUZZING_SEED);

    for (int i = 0; i < 10000; ++i) {
        size_t n = rand() % 4096;

        char src[4096] = {0};
        char expected[4096] = {0};
        char actual[4096] = {0};

        memset(src, rand() % 256, rand() % 4096);

        strncpy(expected, src, n);
        probe_libc_strncpy(actual, src, n);

        cr_assert_arr_eq(actual, expected, n,
        "Expected strncpy result: \"%.*s\", but got: \"%.*s\"",
        (int)n, expected, (int)n, actual);

    }
}



// Normal string with n less than length
Test(strndup, partial_copy) {
    const char *src = "hello world";
    char *dup = probe_libc_strndup(src, 5);

    cr_assert_not_null(dup, "Returned pointer is NULL");
    cr_expect_str_eq(dup, "hello", "Expected 'hello', got '%s'", dup);
    free(dup);
}

// n longer than string
Test(strndup, full_copy_shorter_n) {
    const char *src = "test";
    char *dup = probe_libc_strndup(src, 10);

    cr_assert_not_null(dup);
    cr_expect_str_eq(dup, "test");
    free(dup);
}

// n equal to string length
Test(strndup, exact_length_copy) {
    const char *src = "example";
    char *dup = probe_libc_strndup(src, 7);

    cr_assert_not_null(dup);
    cr_expect_str_eq(dup, "example");
    free(dup);
}

// empty string
Test(strndup, empty_string) {
    const char *src = "";
    char *dup = probe_libc_strndup(src, 5);

    cr_assert_not_null(dup);
    cr_expect_str_eq(dup, "");
    free(dup);
}

// n = 0
Test(strndup, zero_length) {
    const char *src = "non-empty";
    char *dup = probe_libc_strndup(src, 0);

    cr_assert_not_null(dup);
    cr_expect_str_eq(dup, "", "Expected empty string, got '%s'", dup);
    free(dup);
}

// NULL input returns dynamic empty string
Test(strndup, src_null) {
    char *dup = probe_libc_strndup(NULL, 5);
    cr_assert_str_eq(dup, "", "Expected empty string, got '%s'", dup);
}

// Returned string is null-terminated
Test(strndup, string_is_null_terminated) {
    const char *src = "abcdef";
    size_t n = 3;
    char *dup = probe_libc_strndup(src, n);

    cr_assert_not_null(dup);
    cr_expect_eq(dup[n], '\0', "String is not null-terminated");
    free(dup);
}

// Returned string is dynamically allocated (check writable)
Test(strndup, result_is_writable) {
    const char *src = "write test";
    char *dup = probe_libc_strndup(src, 5);

    cr_assert_not_null(dup);
    dup[0] = 'W';  // should not crash
    free(dup);
}

Test(strndup, fuzzing) {
    srand(FUZZING_SEED);

    for (int i = 0; i < 10000; ++i) {
        size_t n = rand() % 4096;

        char src[4096] = {0};
        memset(src, rand() % 256, rand() % 4096);

        char* expected = strndup(src, n);
        char* actual = probe_libc_strndup(src, n);

        cr_assert_str_eq(expected, actual,
        "Expected strndup result: \"%.*s\", but got: \"%.*s\"",
        (int)n, expected, (int)n, actual);

        free(expected);
        free(actual);
    }
}
