#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <sys/stat.h>
#include <dlfcn.h>

static void __attribute__ ((constructor)) init() {
    printf("constructor %d\n", getpid());
}

static void __attribute__ ((destructor)) destructor() {
    printf("destructor %d\n", getpid());
}

static int (*real_open)(const char *, int, mode_t) = 0;

int open(const char *p, int f, mode_t m) {
    if (!real_open) {
        real_open = dlsym(RTLD_NEXT, "open");
    }
    printf("open %d %s %d %d\n", getpid(), p, f, m);
	return real_open(p, f, m);
}
