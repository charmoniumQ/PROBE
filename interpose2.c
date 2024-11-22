/* 2 (cancelled) */
static FILE * unwrapped_fopen (const char *filename, const char *mode) {
    return fopen (filename, mode);
}


/* 2: libc_hooks.h (done) */
static FILE * *(*unwrapped_fopen)(const char *filename, const char *mode);

/* 3: libc_hooks.c init_function_pointers */
{
    unwrapped_fopen = fopen
}

/*
 * 1: libc_hooks.c
 * */
FILE * interpose_fopen (const char *filename, const char *mode) {
    char buffer[256];
    int len = snprintf(buffer, sizeof(buffer),
                       "fopen called with filename: %s, mode: %s\n",
                       filename, mode);
    write(STDERR_FILENO, buffer, len);

    FILE *result = Real__fopen(filename, mode);
    return result;
}

/* 5: libc_hooks.h */


/* 4: libc_hooks.c for every func */
/* static const struct __osx_interpose __osx_interpose_fopen __attribute__((used, section("__DATA, __interpose"))) = { */
/*     (const void*)(uintptr_t)&(__interpose_fopen), */
/*     (const void*)(uintptr_t)&(fopen) */
/* }; */
static const struct __osx_interpose __osx_interpose_fopen = {
    (const void*)(uintptr_t)&(__interpose_fopen),
    (const void*)(uintptr_t)&(fopen)
};
