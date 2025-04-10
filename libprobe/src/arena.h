#pragma once

#define _GNU_SOURCE

#include <stdbool.h>
#include <stddef.h>

struct ArenaListElem;

struct ArenaDir {
    int __dirfd;
    struct ArenaListElem* __tail;
    size_t __next_instantiation;
};

__attribute__((visibility("hidden"))) void* arena_calloc(struct ArenaDir* arena_dir,
                                                         size_t type_count, size_t type_size)
    __attribute__((nonnull, returns_nonnull /*, malloc */));

__attribute__((visibility("hidden"))) void* arena_strndup(struct ArenaDir* arena,
                                                          const char* string, size_t max_size)
    __attribute__((nonnull, returns_nonnull /*, malloc */));

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

__attribute__((visibility("hidden"))) void arena_create(struct ArenaDir* arena_dir,
                                                        int parent_dirfd, char* name,
                                                        size_t capacity) __attribute__((nonnull));

/*
 * Client MUST call arena_destroy or arena_sync for the changes to be saved
 */

__attribute__((visibility("hidden"))) void arena_destroy(struct ArenaDir* arena_dir)
    __attribute__((nonnull));

/*
 * After a fork, we have a copy of the memory, so the arena_dir will be valid and initialized.
 * If CLONE_FILES was not set, we can just call arena_destroy, (incl. munmap() and close()).
 * However, if CLONE_FILES is set, arena_destroy will interfere with the arena in the parent.
 * Therefore, we should NOT close those file descriptors.
 * But we should free the virtual memory mappings for the child.
 * */
__attribute__((visibility("hidden"))) void arena_drop_after_fork(struct ArenaDir* arena_dir)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) void arena_sync(struct ArenaDir* arena_dir)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) void
arena_uninstantiate_all_but_last(struct ArenaDir* arena_dir) __attribute__((nonnull));

__attribute__((visibility("hidden"))) bool arena_is_initialized(struct ArenaDir* arena_dir)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) bool prov_log_is_enabled();
