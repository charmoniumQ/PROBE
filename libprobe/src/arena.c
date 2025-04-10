#define _GNU_SOURCE

#include "../generated/libc_hooks.h"
#include <fcntl.h>
#include <stdalign.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "debug_logging.h"
#include "util.h"

#include "arena.h"

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
struct ArenaListElem;
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

#define ARENA_FNAME_LENGTH 64

static inline void arena_reinstantiate(struct ArenaDir* arena_dir, size_t min_capacity) {
    size_t capacity =
        1 << MAX(ceil_log2(getpagesize()), ceil_log2(min_capacity + sizeof(struct Arena)));

    /* Create a new mmap */
    char fname_buffer[ARENA_FNAME_LENGTH];
    snprintf(fname_buffer, ARENA_FNAME_LENGTH, "%ld.dat", arena_dir->__next_instantiation);
    int fd = unwrapped_openat(arena_dir->__dirfd, fname_buffer, O_RDWR | O_CREAT, 0666);
    ASSERTF(fd > 0, "returned_fd=%d (%s dir_fd=%d) %s", fd, dirfd_path(arena_dir->__dirfd),
            arena_dir->__dirfd, fname_buffer);

    EXPECT(== 0, unwrapped_ftruncate(fd, capacity));

    void* base_address = mmap(NULL, capacity, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
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

    DEBUG(
        "arena_calloc: instantiation of %p, using %ld for Arena, rest starts at %p, capacity %ld\n",
        ARENA_CURRENT->base_address, ARENA_CURRENT->used,
        ARENA_CURRENT->base_address + ARENA_CURRENT->used, ARENA_CURRENT->capacity);

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

void arena_create(struct ArenaDir* arena_dir, int parent_dirfd, char* name, size_t capacity) {
#ifndef NDEBUG
    int ret =
#endif
        unwrapped_mkdirat(parent_dirfd, name, 0777);
#ifndef NDEBUG
    ASSERTF(ret == 0, "(%s fd=%d) %s", dirfd_path(parent_dirfd), parent_dirfd, name);
#endif
    int dirfd = EXPECT(> 0, unwrapped_openat(parent_dirfd, name, O_RDONLY | O_DIRECTORY | O_PATH));
    DEBUG("Creating Arena in (%s fd=%d) which should be (%s fd=%d)/%s", dirfd_path(dirfd), dirfd,
          dirfd_path(parent_dirfd), parent_dirfd, name);

    /* O_DIRECTORY fails if name is not a directory */
    /* O_PATH means the resulting fd cannot be read/written to. It can be used as the dirfd to *at() syscall functions. */
    struct ArenaListElem* tail = EXPECT_NONNULL(malloc(sizeof(struct ArenaListElem)));
    /* malloc here corresponds to free in arena_destroy */

    tail->next_free_slot = 0;
    tail->prev = NULL;
    arena_dir->__dirfd = dirfd;
    arena_dir->__tail = tail;
    arena_dir->__next_instantiation = 0;
    arena_reinstantiate(arena_dir, capacity);
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
                EXPECT(== 0, munmap(arena->base_address, arena->capacity));
                arena = NULL;
            }
        }
        struct ArenaListElem* old_current = current;
        current = current->prev;
        free(old_current);
    }
    arena_dir->__tail = NULL;

    unwrapped_close(arena_dir->__dirfd);
    arena_dir->__dirfd = 0;

    arena_dir->__next_instantiation = 0;
}

void arena_drop_after_fork(struct ArenaDir* arena_dir) {
    struct ArenaListElem* current = arena_dir->__tail;
    while (current) {
        for (size_t i = 0; i < current->next_free_slot; ++i) {
            struct Arena* arena = current->arena_list[i];
            if (arena != NULL) {
                // munmap but no mysnc
                EXPECT(== 0, munmap(arena->base_address, arena->capacity));
                current->arena_list[i] = NULL;
            }
        }
        struct ArenaListElem* old_current = current;
        current = current->prev;
        free(old_current);
    }
    arena_dir->__tail = NULL;
    arena_dir->__dirfd = 0;
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
                EXPECT(== 0, munmap(arena->base_address, arena->capacity));
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
            "is_initialized signals disagree");
    return arena_dir->__tail != NULL;
}
