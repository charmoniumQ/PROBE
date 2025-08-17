
// this exists solely for lsp and will get preprocessed out during build time
#ifndef SRC_INCLUDED
#include <criterion/criterion.h>
#include "probe_libc.h"
#endif

#include <unistd.h>

Test(getid, getpid) {
    cr_assert(getpid() == probe_libc_getpid(), "Expected correct PID");
}

Test(getid, getppid) {
    cr_assert(getppid() == probe_libc_getppid(), "Expected correct PPID");
}

Test(getid, gettid) {
    cr_assert(gettid() == probe_libc_gettid(), "Expected correct TID");
}
