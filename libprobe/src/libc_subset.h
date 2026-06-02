/*
 * We can't #include <stdio.h> in libc_hoks.c because that would give,
 *
 *    generated/libc_hooks.c:1740:16: error: attribute declaration must precede definition [-Werror,-Wignored-attributes]
 *     1740 | __attribute__((visibility("default"))) size_t fread(void * restrict ptr, size_t size, size_t n, FILE * restrict stream)
 *          |                ^
 *    /nix/store/b3pqkywjwzqpq4vi5yffncdbywwpbrmk-glibc-2.33-117-dev/include/bits/stdio2.h:291:1: note: previous definition is here
 *      291 | fread (void *__restrict __ptr, size_t __size, size_t __n,
 *
 * I also can't include anything that includes <stdio.h> and a couple of other libraries.
 *
 * Therefore, this library re-exports the non-overridden parts of stdio.h
 */
struct _IO_FILE;
typedef struct _IO_FILE FILE;
int fprintf(FILE* restrict, const char* restrict, ...);
extern FILE* stderr;
int snprintf(char* restrict, unsigned long, const char* restrict, ...);
int fileno(FILE*);
void free(void*);
void* malloc(unsigned long);
