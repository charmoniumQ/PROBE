#define _GNU_SOURCE

#include "../generated/headers.h" // for OpenNumber
#include <stdbool.h>              // for bool
#include <stdio.h>                // for FILE*
#include <sys/types.h>            // for mode_t

__attribute__((visibility("hidden"))) void prov_log_save();

__attribute__((visibility("hidden"))) void prov_log_record(struct Op op);

/* Could dynamically turn off; also useful for debugging Check to see who
     * actually respects this. I think it is only libc_source_hooks.c will not
     * emit ops. */
__attribute__((visibility("hidden"))) bool prov_log_is_enabled();

__attribute__((visibility("hidden"))) OpenNumber get_open_number(int fd);

__attribute__((visibility("hidden"))) OpenNumber reset_open_number(int fd);

__attribute__((visibility("hidden"))) int open_wrapper(int dirfd, const char* filename, int flags,
                                                       mode_t mode);

__attribute__((visibility("hidden"))) struct Inode get_inode(int fd);

__attribute__((visibility("hidden"))) FILE* fopen_wrapper(const char* filename,
                                                          const char* opentype);

__attribute__((visibility("hidden"))) OpenNumber new_open_number(int fd);

__attribute__((visibility("hidden"))) OpenNumber dup_open_numbers(int old, int new);
