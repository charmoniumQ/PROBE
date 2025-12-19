#define _GNU_SOURCE

#include <stdbool.h> // for bool

struct Op;

__attribute__((visibility("hidden"))) void prov_log_save();

__attribute__((visibility("hidden"))) void prov_log_record(struct Op op);

/* Could dynamically turn off; also useful for debugging Check to see who
     * actually respects this. I think it is only libc_source_hooks.c will not
     * emit ops. */
__attribute__((visibility("hidden"))) bool prov_log_is_enabled();
