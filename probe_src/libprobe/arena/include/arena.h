#pragma once

#define _GNU_SOURCE
#ifdef PYCPARSER
#define __attribute__(x)
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#else
#include <stddef.h>
#include <stdio.h>
#include <stdalign.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#endif

#ifdef ARENA_DEBUG
#define ARENA_PERROR
#endif

#ifndef ARENA_USE_UNWRAPPED_LIBC
#define unwrapped_mkdirat mkdirat
#define unwrapped_openat openat
#define unwrapped_close close
#define unwrapped_ftruncate ftruncate
#endif

#define __ARENA_UNLIKELY(x)     __builtin_expect(!!(x), 0)

struct __Arena {
    size_t instantiation;
    void *base_address;
    uintptr_t capacity;
    uintptr_t used;
};

/* ArenaListElem is a linked-list of arrays of Arenas.
 * The size of the array is ARENA_LIST_BLOCK_SIZE.
 * Making this larger requires more memory, but makes there be fewer linked-list allocations. */
#define ARENA_LIST_BLOCK_SIZE 64
struct __ArenaListElem;
struct __ArenaListElem {
    struct __Arena* arena_list [ARENA_LIST_BLOCK_SIZE];
    /* We store next list elem so that a value of 0 with an uninitialized arena_list represnts a valid ArenaListElem */
    size_t next_free_slot;
    struct __ArenaListElem* prev;
};

struct ArenaDir {
    int __dirfd;
    struct __ArenaListElem* __tail;
    size_t __next_instantiation;
};

static size_t __arena_align(size_t offset, size_t alignment) {
    assert(!(alignment == 0) && !(alignment & (alignment - 1)) && "Alignment must be a power of 2");
    return (offset + alignment - 1) & ~(alignment - 1);
}

#define CURRENT_ARENA arena_dir->__tail->arena_list[arena_dir->__tail->next_free_slot - 1]

#define __ARENA_FNAME_LENGTH 64
#define __ARENA_FNAME "%ld.dat"

/* Instantiate a new mmap-ed file in the arena dir. */
static int __arena_reinstantiate(struct ArenaDir* arena_dir, size_t capacity) {
    /* Create a new mmap */
    char fname_buffer [__ARENA_FNAME_LENGTH];
    snprintf(fname_buffer, __ARENA_FNAME_LENGTH, __ARENA_FNAME, arena_dir->__next_instantiation);
    int fd = unwrapped_openat(arena_dir->__dirfd, fname_buffer, O_RDWR | O_CREAT, 0666);
    if (fd < 0) {
#ifdef ARENA_PERROR
        perror("__arena_reinstantiate: openat");
#endif
        return -1;
    }
    int ret = unwrapped_ftruncate(fd, capacity);
    if (ret != 0) {
#ifdef ARENA_PERROR
        perror("__arena_reinstantiate: ftruncate");
#endif
        return -1;
    }
    void* base_address = mmap(NULL, capacity, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    /* mmap here corresponds to munmap in either arena_destroy or arena_uninstantiate_all_but_last */
    if (base_address == MAP_FAILED) {
        unwrapped_close(fd);
#ifdef ARENA_PERROR
        perror("__arena_reinstantiate: mmap");
#endif
        return -1;
    }
    unwrapped_close(fd);


    if (arena_dir->__tail->next_free_slot == ARENA_LIST_BLOCK_SIZE) {
        /* Out of free slots in this block.
         * We need to allocate a new linked-list node
         * */
        struct __ArenaListElem* old_tail = arena_dir->__tail;
        arena_dir->__tail = malloc(sizeof(struct __ArenaListElem));
        /* This malloc is undone by a free in arena_dir_destroy */

        /* We are about to use slot 0, so the next free slot would be 1 */
        arena_dir->__tail->next_free_slot = 1;
        arena_dir->__tail->prev = old_tail;
    } else {
        /* Mark this slot as used */
        arena_dir->__tail->next_free_slot++;
    }

    /* Either way, we just have to assign a new slot in the current linked-list node. */
    CURRENT_ARENA = base_address;

    /* struct __Arena has to be the first thing in the __Arena, which does take up some size */
    /* This stuff shows up in the __Arena file */
    CURRENT_ARENA->instantiation = arena_dir->__next_instantiation;
    CURRENT_ARENA->base_address = base_address;
    CURRENT_ARENA->capacity = capacity;
    CURRENT_ARENA->used = sizeof(struct __Arena);

#ifdef ARENA_DEBUG
        fprintf(
            stderr,
            "arena_calloc: instantiation of %p, using %ld for __Arena, rest starts at %p\n",
            CURRENT_ARENA->base_address,
            CURRENT_ARENA->used,
            CURRENT_ARENA->base_address + CURRENT_ARENA->used
        );
#endif

    /* Update for next instantiation */
    arena_dir->__next_instantiation++;

    return 0;
}

#define __ARENA_MAX(a, b) ((a) < (b) ? (b) : (a))

static void* arena_calloc(struct ArenaDir* arena_dir, size_t type_count, size_t type_size) {
    size_t padding = __arena_align(CURRENT_ARENA->used, _Alignof(void*)) - CURRENT_ARENA->used;
    if (CURRENT_ARENA->used + padding + type_count * type_size > CURRENT_ARENA->capacity) {
#ifdef ARENA_DEBUG
        fprintf(
            stderr,
            "arena_calloc: Current arena (at %p, used %ld / %ld) is too small for allocation of %ld * %ld + %ld = %ld\n",
            CURRENT_ARENA->base_address, CURRENT_ARENA->used, CURRENT_ARENA->capacity,
            type_count,
            type_size,
            padding,
            padding + type_count * type_size
        );
#endif
        /* Current arena is too small for this allocation;
         * Let's allocate a new one. */
        int ret = __arena_reinstantiate(arena_dir, __ARENA_MAX(CURRENT_ARENA->capacity, type_count * type_size + sizeof(struct __Arena)));
        if (ret != 0) {
#ifdef ARENA_PERROR
            fprintf(stderr, "arena_calloc: arena_reinstantiate failed\n");
#endif
            return NULL;
        }
        padding = 0;
        assert(CURRENT_ARENA->used + padding + type_count * type_size <= CURRENT_ARENA->capacity);
    }
#ifdef ARENA_DEBUG
        fprintf(
            stderr,
            "arena_calloc: allocation of %ld * %ld + %ld = %ld, %p -> %p <--> %p\n",
            type_count,
            type_size,
            padding,
            padding + type_count * type_size,
            CURRENT_ARENA->base_address + CURRENT_ARENA->used,
            CURRENT_ARENA->base_address + CURRENT_ARENA->used + padding,
            CURRENT_ARENA->base_address + CURRENT_ARENA->used + padding + type_count * type_size
        );
#endif
    void* ret = CURRENT_ARENA->base_address + CURRENT_ARENA->used + padding;
    CURRENT_ARENA->used = CURRENT_ARENA->used + padding + type_count * type_size;
    ((char*)ret)[0] = '\0'; /* Test memory is valid */
    return ret;
}

__attribute__((unused)) static void* arena_strndup(struct ArenaDir* arena, const char* string, size_t max_size) {
    size_t length = strnlen(string, max_size);
    char* dst = arena_calloc(arena, length + 1, sizeof(char));
    if (dst) {
        memcpy(dst, string, length + 1);
    } else {
#ifdef ARENA_PERROR
        fprintf(stderr, "arena_strndup: arena_calloc failed\n");
#endif
    }
    return dst;
}

static unsigned char __ARENA_PAGE_SIZE = 0;
static int arena_create(struct ArenaDir* arena_dir, int parent_dirfd, char* name, size_t capacity) {
    if (__ARENA_UNLIKELY(__ARENA_PAGE_SIZE == 0)) {
        __ARENA_PAGE_SIZE = sysconf(_SC_PAGESIZE);
    }
    if (unwrapped_mkdirat(parent_dirfd, name, 0777) != 0) {
#ifdef ARENA_PERROR
        perror("arena_create: mkdirat");
#endif
        return -1;
    }
    int dirfd = unwrapped_openat(parent_dirfd, name, O_RDONLY | O_DIRECTORY | O_PATH);
    if (dirfd < 0) {
#ifdef ARENA_PERROR
        perror("arena_create: openat");
#endif
        return -1;
    }
    /* O_DIRECTORY fails if name is not a directory */
    /* O_PATH means the resulting fd cannot be read/written to. It can be used as the dirfd to *at() syscall functions. */
    struct __ArenaListElem* tail = malloc(sizeof(struct __ArenaListElem));
    if (!tail) {
#ifdef ARENA_PERROR
        perror("arena_create: malloc");
#endif
        return -1;
    }
    /* malloc here corresponds to free in arena_destroy */
    tail->next_free_slot = 0;
    tail->prev = NULL;
    arena_dir->__dirfd = dirfd;
    arena_dir->__tail = tail;
    arena_dir->__next_instantiation = 0;
    int ret = __arena_reinstantiate(arena_dir, capacity);
    if (ret != 0) {
        return ret;
    }
    return 0;
}

__attribute__((unused)) static int arena_destroy(struct ArenaDir* arena_dir) {
    struct __ArenaListElem* current = arena_dir->__tail;
    while (current) {
        for (size_t i = 0; i < current->next_free_slot; ++i) {
            if (current->arena_list[i] != NULL) {
                int ret = munmap(current->arena_list[i]->base_address, current->arena_list[i]->capacity);
                if (ret != 0) {
#ifdef ARENA_PERROR
                    perror("arena_create: arena_destroy");
#endif
                    return -1;
                }
                current->arena_list[i] = NULL;
            }
        }
        struct __ArenaListElem* old_current = current;
        current = current->prev;
        free(old_current);
    }
    arena_dir->__tail = NULL;

    unwrapped_close(arena_dir->__dirfd);
    arena_dir->__dirfd = 0;

    arena_dir->__next_instantiation = 0;

    return 0;
}

/*
 * After a fork, we have a copy of the memory, so the arena_dir will be valid and initialized.
 * If CLONE_FILES was not set, we can just call arena_destroy.
 * However, if CLONE_FILES is set, arena_destroy will interfere with the arena in the parent.
 * Therefore, we should NOT close those file descriptors.
 * But we should free the virtual memory mappings.
 * */
__attribute__((unused)) static int arena_drop_after_fork(struct ArenaDir* arena_dir) {
    struct __ArenaListElem* current = arena_dir->__tail;
    while (current) {
        for (size_t i = 0; i < current->next_free_slot; ++i) {
            if (current->arena_list[i] != NULL) {
                int ret = munmap(current->arena_list[i]->base_address, current->arena_list[i]->capacity);
                if (ret != 0) {
#ifdef ARENA_PERROR
                    perror("arena_create: arena_uninstantiate_all_but_last");
#endif
                    return -1;
                }
                current->arena_list[i] = NULL;
            }
        }
        struct __ArenaListElem* old_current = current;
        current = current->prev;
        free(old_current);
    }
    arena_dir->__tail = NULL;
    arena_dir->__dirfd = 0;
    arena_dir->__next_instantiation = 0;

    return 0;
}

__attribute__((unused)) static int arena_uninstantiate_all_but_last(struct ArenaDir* arena_dir) {
    struct __ArenaListElem* current = arena_dir->__tail;
    bool is_tail = true;
    while (current) {
        for (size_t i = 0; i + ((size_t) is_tail) < current->next_free_slot; ++i) {
            if (current->arena_list[i] != NULL) {
                int ret = munmap(current->arena_list[i]->base_address, current->arena_list[i]->capacity);
                if (ret != 0) {
#ifdef ARENA_PERROR
                    perror("arena_create: arena_uninstantiate_all_but_last");
#endif
                    return -1;
                }
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
    return 0;
}

__attribute__((unused)) static bool arena_is_initialized(struct ArenaDir* arena_dir) {
    assert(
        (arena_dir->__tail == NULL) == (arena_dir->__next_instantiation == 0)
    );
    return arena_dir->__tail != NULL;
}
