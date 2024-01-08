#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <stdbool.h>

extern bool initialized = false;
void __attribute__ ((constructor)) setup() {
    printf("constructor %d %d %d\n", getpid(), gettid(), initialized);
    initialized = true;
}

/* bool initialized2 = false; */
/* void setup_once() { */
/*     if (!initialized2) { */
/*         printf("setup\n"); */
/*         initialized2 = true; */
/*     } */
/* } */

/* #include <dlfcn.h> */
/* int (*real_open)(const char*, int); */

/* int open(const char *pathname, int flags) { */
/*     fprintf(stderr, "open(%s, %d)\n", pathname, flags); */
/*     if (!real_open) { */
/*         real_open = dlsym(RTLD_NEXT, "open"); */
/*     } */
/*     setup_once(); */
/*     return real_open(pathname, flags); */
/* } */
