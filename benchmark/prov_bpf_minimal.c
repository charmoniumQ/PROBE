#include <unistd.h>
#include <stdio.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#define EXPECT_ZERO(expr) ({\
            int ret = expr; \
            if (expr != 0) { \
                fprintf(stderr, "failure on line %d: %s\nreturned a non-zero, %d\nstrerror: %s\n", __LINE__, #expr, ret, strerror(errno)); \
                abort(); \
            } \
            ret; \
    })

char* bpftrace_exe = "/home/sam/box/prov/benchmark/result/bin/bpftrace";

int main() {
    uid_t unprivileged_user = getuid();
    uid_t unprivileged_group = getgid();
    uid_t privileged_user = geteuid();
    uid_t privileged_group = getegid();
    EXPECT_ZERO(setreuid(privileged_user, privileged_user));
    EXPECT_ZERO(setregid(privileged_group, privileged_group));
    EXPECT_ZERO(execl(bpftrace_exe, bpftrace_exe, "-l", "tracepoint:*", NULL));
    return 0;
}
