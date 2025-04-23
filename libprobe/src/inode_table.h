#pragma once

#define _GNU_SOURCE

#include <stdbool.h> // for bool

struct Path;

/*
 * This struct "hides" the implementation from users.
 * They don't know about IndexTable or how it is implemented; just functions beginning with inode_table_*.
 * */
struct InodeTable {
    struct IndexTable* majors;
};

__attribute__((visibility("hidden"))) void inode_table_init(struct InodeTable* inode_table)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) bool inode_table_is_init(struct InodeTable* inode_table)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) bool inode_table_contains(struct InodeTable* inode_table,
                                                                const struct Path* path)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) bool
inode_table_put_if_not_exists(struct InodeTable* inode_table, const struct Path* path)
    __attribute__((nonnull));
