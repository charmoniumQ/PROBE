#ifndef LINUX_DEFINES_H
#define LINUX_DEFINES_H

#define _GNU_SOURCE
#include <stdbool.h>
#include <linux/limits.h>
#include <malloc.h>
#include <sys/sysmacros.h>
#include <threads.h>
#include <sys/syscall.h>


static inline int fstatat64(int dirfd, const char *pathname, struct stat64 *buf, int flags) {
    return fstatat(dirfd, pathname, buf, flags);
}
static __thread bool __thread_inited = false;


#endif
