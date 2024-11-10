#ifndef LINUX_DEFINES_H
#define LINUX_DEFINES_H

#include <stdbool.h>
#include <linux/limits.h>
#include <malloc.h>
#include <sys/sysmacros.h>
#include <threads.h>
#include <sys/syscall.h>

#define THREAD_LOCAL __thread

static THREAD_LOCAL bool __thread_inited = false;

#endif
