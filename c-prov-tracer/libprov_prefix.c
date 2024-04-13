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
#include <sys/resource.h>

/*
 * I can't include unistd.h because it also defines dup3.
 */
pid_t getpid(void);
pid_t gettid(void);

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
        EXPECT(, __prov_log_head = __prov_log_tail = malloc(sizeof(struct __ProvLogCell)));
        __prov_log_head->next = NULL;
    }
    assert(__prov_log_tail->capacity <= __prov_log_cell_size);
    if (__prov_log_tail->capacity == __prov_log_cell_size) {
        /* Not first time, but old one is full */
        struct __ProvLogCell* old_tail = __prov_log_tail;
        EXPECT(, __prov_log_tail = malloc(sizeof(struct __ProvLogCell)));
        __prov_log_tail->next = NULL;
        old_tail->next = __prov_log_tail;
    }
    /* TODO: Figure out workarounds for this copy */
    /* We will duplicate this string, because it could disappear from the tracee's stack at any time. */
    char* new_raw_path = strdup(op.path.raw_path);
    op.path.raw_path = new_raw_path;
    __prov_log_tail->ops[__prov_log_tail->capacity] = op;
    fprintf_op(stderr, op);
    ++__prov_log_tail->capacity;
}
