#pragma once

#include <stdbool.h>
#include <linux/limits.h>
#include <malloc.h>
#include <sys/sysmacros.h>
#include <threads.h>
#include <sys/syscall.h>

static __thread bool __thread_inited = false;

#define platform_independent_execvpe execvpe

#define
