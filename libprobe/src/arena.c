#define _GNU_SOURCE

#include "arena.h"

#include <fcntl.h>    // for AT_FDCWD, O_CREAT, O_RDWR
#include <stdbool.h>  // for bool, false, true
#include <stddef.h>   // for size_t, NULL
#include <stdint.h>   // for uintptr_t
#include <stdio.h>    // for snprintf
#include <stdlib.h>   // for free, malloc
#include <string.h>   // for memcpy, strnlen
#include <sys/mman.h> // for msync, munmap, MAP_FAILED, MS_SYNC, MAP_SHARED, PROT_READ
#include <unistd.h>   // for getpagesize
// IWYU pragma: no_include "bits/mman-linux.h"          for MS_SYNC, MAP_SHARED, PROT_READ

#include "../generated/libc_hooks.h" // for unwrapped_close, unwrapped_ftru...
#include "debug_logging.h"           // for EXPECT, ASSERTF, EXPECT_NONNULL
#include "util.h"                    // for ceil_log2, MAX

/* TODO: Interpose munmap. See global_state.c, ../generator/libc_hooks_source.c */
#define unwrapped_munmap munmap

struct Arena {
    size_t instantiation;
    void* base_address;
    uintptr_t capacity;
    uintptr_t used;
};

/* ArenaListElem is a linked-list of arrays of Arenas.
 * The size of the array is ARENA_LIST_BLOCK_SIZE.
 * Making this larger requires more memory, but makes there be fewer linked-list allocations. */
#define ARENA_LIST_BLOCK_SIZE 64
struct ArenaListElem {
    struct Arena* arena_list[ARENA_LIST_BLOCK_SIZE];
    /* We store next list elem so that a value of 0 with an uninitialized arena_list represnts a valid ArenaListElem */
    size_t next_free_slot;
    struct ArenaListElem* prev;
};

static inline size_t __arena_align(size_t offset, size_t alignment) {
    ASSERTF(!(alignment == 0) && !(alignment & (alignment - 1)), "Alignment must be a power of 2");
    return (offset + alignment - 1) & ~(alignment - 1);
}

#define ARENA_CURRENT arena_dir->__tail->arena_list[arena_dir->__tail->next_free_slot - 1]

static inline void arena_reinstantiate(struct ArenaDir* arena_dir, size_t min_capacity) {
    size_t capacity =
        1 << MAX(ceil_log2(getpagesize()), ceil_log2(min_capacity + sizeof(struct Arena)));

    /* Create a new mmap */
    snprintf(arena_dir->__dir_buffer + arena_dir->__dir_len,
             arena_dir->__dir_buffer_max - arena_dir->__dir_len, "%016lx.dat",
             arena_dir->__next_instantiation);
    int fd = unwrapped_openat(AT_FDCWD, arena_dir->__dir_buffer, O_RDWR | O_CREAT, 0666);
    ASSERTF(fd > 0, "returned_fd=%d (%s)", fd, arena_dir->__dir_buffer);

    EXPECT(== 0, unwrapped_ftruncate(fd, capacity));

    void* base_address = unwrapped_mmap(NULL, capacity, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    ASSERTF(base_address != MAP_FAILED, "");
    /* mmap here corresponds to munmap in either arena_destroy or arena_uninstantiate_all_but_last */

    EXPECT(== 0, unwrapped_close(fd));

    if (arena_dir->__tail->next_free_slot == ARENA_LIST_BLOCK_SIZE) {
        /* No more free slots in this block, as we've reached block size.
         * We need to allocate a new linked-list node
         * */
        struct ArenaListElem* old_tail = arena_dir->__tail;
        arena_dir->__tail = EXPECT_NONNULL(malloc(sizeof(struct ArenaListElem)));
        /* This malloc is undone by a free in arena_dir_destroy */

        /* We are about to use slot 0, so the next free slot would be 1 */
        arena_dir->__tail->next_free_slot = 1;
        arena_dir->__tail->prev = old_tail;
    } else {
        /* Mark this slot as used */
        arena_dir->__tail->next_free_slot++;
    }

    /* Either way, we just have to assign a new slot in the current linked-list node. */
    ARENA_CURRENT = base_address;

    /* struct Arena has to be the first thing in the Arena, which does take up some size */
    /* This stuff shows up in the Arena file */
    ARENA_CURRENT->instantiation = arena_dir->__next_instantiation;
    ARENA_CURRENT->base_address = base_address;
    ARENA_CURRENT->capacity = capacity;
    ARENA_CURRENT->used = sizeof(struct Arena);

    DEBUG("arena_calloc: instantiation=%ld, base_address=%p, used=%ld, capacity=%ld",
          ARENA_CURRENT->instantiation, ARENA_CURRENT->base_address, ARENA_CURRENT->used,
          ARENA_CURRENT->capacity);

    /* Update for next instantiation */
    arena_dir->__next_instantiation++;
}

void* arena_calloc(struct ArenaDir* arena_dir, size_t type_count, size_t type_size) {
    size_t padding = __arena_align(ARENA_CURRENT->used, _Alignof(void*)) - ARENA_CURRENT->used;
    if (ARENA_CURRENT->used + padding + type_count * type_size > ARENA_CURRENT->capacity) {
        /* Current arena is too small for this allocation;
         * Let's allocate a new one. */
        arena_reinstantiate(
            arena_dir, MAX(ARENA_CURRENT->capacity, type_count * type_size + sizeof(struct Arena)));
        padding = 0;
        ASSERTF(ARENA_CURRENT->used + padding + type_count * type_size <= ARENA_CURRENT->capacity,
                "Capacity calculation is wrong (%ld + %ld + %ld * %ld should be <= %ld)",
                ARENA_CURRENT->used, padding, type_count, type_size, ARENA_CURRENT->capacity);
    }

    void* ret = ARENA_CURRENT->base_address + ARENA_CURRENT->used + padding;
    ARENA_CURRENT->used = ARENA_CURRENT->used + padding + type_count * type_size;
    ((char*)ret)[0] = '\0'; /* Test memory is valid */
    return ret;
}

void* arena_strndup(struct ArenaDir* arena, const char* string, size_t max_size) {
    size_t length = strnlen(string, max_size);
    char* dst = EXPECT_NONNULL(arena_calloc(arena, length + 1, sizeof(char)));
    memcpy(dst, string, length + 1);
    return dst;
}

void arena_create(struct ArenaDir* arena_dir, char* dir_buffer, size_t dir_len,
                  size_t dir_buffer_max, size_t arena_capacity) {
    EXPECT(== 0, unwrapped_mkdirat(AT_FDCWD, dir_buffer, 0777));
    struct ArenaListElem* tail = EXPECT_NONNULL(malloc(sizeof(struct ArenaListElem)));
    /* malloc here corresponds to free in arena_destroy */

    tail->next_free_slot = 0;
    tail->prev = NULL;
    arena_dir->__dir_buffer = dir_buffer;
    arena_dir->__dir_len = dir_len;
    arena_dir->__dir_buffer_max = dir_buffer_max;
    arena_dir->__tail = tail;
    arena_dir->__next_instantiation = 0;
    arena_reinstantiate(arena_dir, arena_capacity);
}

/*
 * - msync is required, from [a previous issue](https://github.com/charmoniumQ/PROBE/pull/84) as well.
 *
 *  > Without use of this call, there is no guarantee that changes are
 *    written back before munmap(2) is called. --- [man msync](https://www.man7.org/linux/man-pages/man2/msync.2.html)
 */

void arena_destroy(struct ArenaDir* arena_dir) {
    struct ArenaListElem* current = arena_dir->__tail;
    while (current) {
        for (size_t i = 0; i < current->next_free_slot; ++i) {
            struct Arena* arena = current->arena_list[i];
            if (arena != NULL) {
                EXPECT(== 0, msync(arena->base_address, arena->capacity, MS_SYNC));
                EXPECT(== 0, unwrapped_munmap(arena->base_address, arena->capacity));
                arena = NULL;
            }
        }
        struct ArenaListElem* old_current = current;
        current = current->prev;
        free(old_current);
    }
    arena_dir->__tail = NULL;
    arena_dir->__next_instantiation = 0;
}

void arena_drop_after_fork(struct ArenaDir* arena_dir) {
    struct ArenaListElem* current = arena_dir->__tail;
    while (current) {
        for (size_t i = 0; i < current->next_free_slot; ++i) {
            struct Arena* arena = current->arena_list[i];
            if (arena != NULL) {
                // munmap but no mysnc
                EXPECT(== 0, unwrapped_munmap(arena->base_address, arena->capacity));
                current->arena_list[i] = NULL;
            }
        }
        struct ArenaListElem* old_current = current;
        current = current->prev;
        free(old_current);
    }
    arena_dir->__tail = NULL;
    arena_dir->__next_instantiation = 0;
}

void arena_sync(struct ArenaDir* arena_dir) {
    struct ArenaListElem* current = arena_dir->__tail;
    while (current) {
        for (size_t i = 0; i < current->next_free_slot; ++i) {
            struct Arena* arena = current->arena_list[i];
            if (arena != NULL) {
                // msync but no mmunmap
                EXPECT(== 0, msync(arena->base_address, arena->capacity, MS_SYNC));
            }
        }
        current = current->prev;
    }
}

void arena_uninstantiate_all_but_last(struct ArenaDir* arena_dir) {
    struct ArenaListElem* current = arena_dir->__tail;
    bool is_tail = true;
    while (current) {
        for (size_t i = 0; i + ((size_t)is_tail) < current->next_free_slot; ++i) {
            struct Arena* arena = current->arena_list[i];
            if (arena != NULL) {
                EXPECT(== 0, msync(arena->base_address, arena->capacity, MS_SYNC));
                EXPECT(== 0, unwrapped_munmap(arena->base_address, arena->capacity));
                current->arena_list[i] = NULL;
            }
        }
        if (!is_tail) {
            /* Setting to zero means it gets skipped next time we try to uninstantiate */
            current->next_free_slot = 0;
        }
        is_tail = false;
        current = current->prev;
    }
}

bool arena_is_initialized(struct ArenaDir* arena_dir) {
    ASSERTF((arena_dir->__next_instantiation == 0) == (arena_dir->__tail == NULL),
            "is_initialized signals disagree %ld %p", arena_dir->__next_instantiation,
            arena_dir->__tail);
    return arena_dir->__tail != NULL;
}
