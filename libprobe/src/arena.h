#pragma once

#define _GNU_SOURCE

#include <stdbool.h> // for bool
#include <stddef.h>  // for size_t
#include "../generated/headers.h"
#include "../src/probe_libc.h"

struct ArenaDir {
    char* _Nonnull __dir_buffer;
    size_t __dir_len;
    size_t __dir_buffer_max;
    struct ArenaListElem* _Nonnull __tail;
    size_t __next_instantiation;
};

__attribute__((visibility("hidden"))) void* _Nonnull arena_calloc(struct ArenaDir* _Nonnull arena_dir,
                                                         size_t type_count, size_t type_size);

__attribute__((visibility("hidden"))) void* _Nonnull arena_strndup(struct ArenaDir* _Nonnull arena,
                                                          const char* _Nonnull string, size_t max_size);

/* A note on malloc attribute:
 *
 * > Attribute malloc indicates that a function is malloc-like, i.e., that the pointer P returned by the function cannot alias any other pointer valid when the function returns...
 * >
 * > --- [GCC Manual 6.4.1 Common Function Attributes](https://gcc.gnu.org/onlinedocs/gcc/Common-Function-Attributes.html)
 *
 * Sounds applicable, right?
 *
 * Nope. If we never read from the pointer returned by calloc, GCC can optimize out stores to that pointer.
 *
 * Implicitly, the pointer *is* read when the mmap gets synced and closed, despite not having a direct "use" of the pointer returned by arena_calloc.
 * */

__attribute__((visibility("hidden"))) void
arena_create(struct ArenaDir* _Nonnull arena_dir, char* _Nonnull dir_buffer, size_t dir_len, size_t dir_buffer_max,
             size_t arena_capacity);

/*
 * Client MUST call arena_destroy or arena_sync for the changes to be saved
 */

__attribute__((visibility("hidden"))) void arena_destroy(struct ArenaDir* _Nonnull arena_dir);

/*
 * After a fork, we have a copy of the memory, so the arena_dir will be valid and initialized.
 * If CLONE_FILES was not set, we can just call arena_destroy, (incl. munmap() and close()).
 * However, if CLONE_FILES is set, arena_destroy will interfere with the arena in the parent.
 * Therefore, we should NOT close those file descriptors.
 * But we should free the virtual memory mappings for the child.
 * */
__attribute__((visibility("hidden"))) void arena_drop_after_fork(struct ArenaDir* _Nonnull arena_dir);

__attribute__((visibility("hidden"))) void arena_sync(struct ArenaDir* _Nonnull arena_dir);

__attribute__((visibility("hidden"))) void
arena_uninstantiate_all_but_last(struct ArenaDir* _Nonnull arena_dir);

__attribute__((visibility("hidden"))) bool arena_is_initialized(struct ArenaDir* _Nonnull arena_dir);


/* Copy char* const argv[] into the arena.
 * If argc argument is 0, compute argc and store there (if the size actually was zero, this is no bug).
 * If argc argument is positive, assume that is the argc.
 * */
__attribute__((visibility("hidden"))) StringArray arena_copy_argv(
    struct ArenaDir* _Nonnull arena_dir, char const* _Nullable const* _Nonnull argv, size_t argc);

__attribute__((visibility("hidden"))) StringArray
arena_copy_cmdline(struct ArenaDir* _Nonnull arena_dir, result_sized_mem cmdline);

