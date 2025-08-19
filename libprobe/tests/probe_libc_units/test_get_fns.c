
// this exists solely for lsp and will get preprocessed out during build time
#ifndef SRC_INCLUDED
#include <criterion/criterion.h>
#include "probe_libc.h"
#endif

#include <errno.h>
#include <linux/limits.h>
#include <stddef.h>
#include <unistd.h>

extern char** environ;

Test(get, getpid) {
    cr_assert(getpid() == probe_libc_getpid(), "Expected correct PID");
}

Test(get, getppid) {
    cr_assert(getppid() == probe_libc_getppid(), "Expected correct PPID");
}

Test(get, gettid) {
    cr_assert(gettid() == probe_libc_gettid(), "Expected correct TID");
}

Test(get, getpagesize, .init = setup) {
    cr_assert((size_t)getpagesize() == probe_libc_getpagesize(), "Expected correct page size");
}

// this is not exactly a complete test of getcwd, but for a function this
// simple (as compared to the mem* functions) unit tests are mostly just a
// sanity check
Test(get, getcwd) {
    char buf[PATH_MAX] = {0};
    char expected[PATH_MAX] = {0};
    char actual[PATH_MAX] = {0};

    char* ret1 = getcwd(expected, PATH_MAX);
    int e = errno;
    strncpy(buf, strerror(e), PATH_MAX);
    cr_assert_not_null(ret1, "getcwd errored with %s (%d)", buf, e);

    result_str ret2 = probe_libc_getcwd(actual, PATH_MAX);
    strncpy(buf, strerror(ret2.error), PATH_MAX);
    cr_assert(ret2.error == 0, "probe_libc_getcwd errored with %s (%d)", buf, ret2.error);

    cr_assert_str_eq(actual, expected, "got cwd %s but expected %s", actual, expected);
}

// technically the order of envrion isn't guaranteed, but every sane
// implementation (including ours) processes them in the order the kernel gives
// them to you, and i'd rather the test overconstrain than underconstrain
Test(get, environ, .init = setup) {
    for (size_t i = 0; environ[i] != NULL; ++i) {
        cr_assert_not_null(probe_environ[i], "Expected %s but got NULL", environ[i]);
        cr_assert_str_eq(environ[i], probe_environ[i], "Expected %s but got %s", environ[i], probe_environ[i]);
    }
}

Test(get, getenv, .init = setup) {
    for (size_t i = 0; environ[i] != NULL; ++i) {
        const char* curr = environ[i];

        size_t n = 0;
        for (; curr[n] != '=' ; ++n);
        char* name = strndup(curr, n);

        const char* expected = getenv(name);
        const char* actual = probe_libc_getenv(name);

        cr_assert_not_null(actual, "Got NULL for name %s", name);
        cr_assert_str_eq(expected, actual, "Expected %s but got %s for name %s", expected, actual, name);
    }
}
