#define _GNU_SOURCE

#include "../include/libprobe/prov_ops.h"

__attribute__((visibility("hidden")))
void prov_log_save();

/*
 * 1. call prov_log_try(op)
 * 2. actually execute lib call
 * 3. fill in details from return value into op
 * 4. call prov_log_record(op)
 */
__attribute__((visibility("hidden")))
void prov_log_try(struct Op op);
__attribute__((visibility("hidden")))
void prov_log_record(struct Op op);

/* Could dynamically turn off; also useful for debugging Check to see who
     * actually respects this. I think it is only libc_source_hooks.c will not
     * emit ops. */
__attribute__((visibility("hidden")))
bool prov_log_is_enabled();
