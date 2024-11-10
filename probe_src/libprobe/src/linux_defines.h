#ifndef LINUX_DEFINES_H
#define LINUX_DEFINES_H

#include <stdbool.h>
#include <linux/limits.h>
#include <malloc.h>
#include <sys/sysmacros.h>
#include <threads.h>
#include <sys/syscall.h>

#define THREAD_LOCAL __thread

#ifndef HAVE_FSTATAT64
static inline int fstatat64(int dirfd, const char *pathname, struct stat64 *buf, int flags) {
    return fstatat(dirfd, pathname, buf, flags);
}
#endif

static THREAD_LOCAL bool __thread_inited = false;

#endif
