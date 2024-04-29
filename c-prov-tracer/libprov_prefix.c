#define _GNU_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <errno.h>
#include <linux/limits.h>
#include <errno.h>
#include <dlfcn.h>
#include <sys/types.h>
#include <dirent.h>
#include <ftw.h>
#include <stdarg.h>
#include <sys/resource.h>
#include <pthread.h>

/*
 * I can't include unistd.h because it also defines dup3.
 */
pid_t getpid(void);
pid_t gettid(void);
struct utimbuf;

/*
 * OWNED/BORROWED determins who is responsible for freeing a pointer received or returned by a function-call.
 * Obviously, this is inspired by Rust.
 * C compiler can't check this at compile-time, but these macros serve to document the function-signatures for humans.
 * E.g.,
 *
 *     OWNED int* copy_int(BORROWED int*)
 *
 * If a function-call returns an OWNED pointer, the callee has to free it.
 * If a function-call receives an OWNED pointer, the callee can't use it after the call.
 * If a function-call returns a BORROWED pointer, the callee can't free it.
 * If a function-call receives a BORROWED pointer, the function can't free it.
 * */
#define OWNED
#define BORROWED

#define EXPECT(cond, expr) ({\
    size_t ret = (size_t) (expr); \
    if (!(ret cond)) { \
        fprintf(stderr, "failure on %s:%d: %s: !(%ld %s)\nstrerror: %s\n", __FILE__, __LINE__, #expr, ret, #cond, strerror(errno)); \
        abort(); \
    } \
    ret; \
})

static __thread bool __prov_log_disable = false;

static void prov_log_disable() { __prov_log_disable = true; }
static void prov_log_enable () { __prov_log_disable = false; }
static bool prov_log_is_enabled () { return !__prov_log_disable; }

static void prov_log_save(void);

/* static char getname_buffer[PATH_MAX]; */
/* static char* getname(const FILE* file); */

#include "prov_operations.c"

#define __prov_log_cell_size (10 * 1024)
struct __ProvLogCell {
    size_t capacity;
    struct Op ops[__prov_log_cell_size];
    struct __ProvLogCell* next;
};

static __thread struct __ProvLogCell* __prov_log_tail = NULL;
static __thread struct __ProvLogCell* __prov_log_head = NULL;

static void prov_log_record(struct Op op) {
    if (__prov_log_tail == NULL) {
        /* First time! Allocate new buffer */
        assert(__prov_log_head == NULL);
        /* This allocation is mirrored by a free in prov_log_save. */
        EXPECT(, __prov_log_head = __prov_log_tail = malloc(sizeof(struct __ProvLogCell)));
        __prov_log_head->next = NULL;
    }
    assert(__prov_log_tail->capacity <= __prov_log_cell_size);
    if (__prov_log_tail->capacity == __prov_log_cell_size) {
        /* Not first time, but old one is full */
        struct __ProvLogCell* old_tail = __prov_log_tail;
        /* This allocation is mirrored by a free in prov_log_save. */
        EXPECT(, __prov_log_tail = malloc(sizeof(struct __ProvLogCell)));
        __prov_log_tail->next = NULL;
        old_tail->next = __prov_log_tail;
    }
    /*
     * I'm not sure how to describe that op.path.raw_path is BORROWED... but it is!
     * It comes from an argument passed to open(...) or whatever function we just intercepted.
     * This means it comes from the tracee's stack, and can disappear at any time.
     * Since we want to hold this op longer than the function-call we intercepted, we must make a copy.
     *
     * This allocation is mirrored by a free(...) in prov_log_save.
     * */
    if (op.path.raw_path) {
        char* new_raw_path = strdup(op.path.raw_path);
        op.path.raw_path = new_raw_path;
    }
    __prov_log_tail->ops[__prov_log_tail->capacity] = op;
    //fprintf_op(stderr, op);
    ++__prov_log_tail->capacity;
}

static OWNED char* lookup_on_path(BORROWED const char* bin_name);

/*
 * pycparser cannot parse type-names as function-arguments (as in `va_arg(var_name, type_name)`)
 * so we use some macros instead.
 * To pycparser, these macros are defined as variable names (parsable as arguments).
 * To GCC these macros are defined as type names.
 * */
#define __type_mode_t mode_t
