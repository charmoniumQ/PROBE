#pragma once

#define _GNU_SOURCE

#include "util.h"    // for BORROWED
#include <stdbool.h> // for bool
#include "include/libprobe/prov_ops.h"

struct rusage;
struct stat;
struct statx;

__attribute__((visibility("hidden"))) struct Path
create_path_lazy(int dirfd, BORROWED const char* path, int flags);

__attribute__((visibility("hidden"))) void path_to_id_string(const struct Path* path,
                                                             BORROWED char* string)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) void do_init_ops(bool was_epoch_initted);

__attribute__((visibility("hidden"))) const struct Path* op_to_path(const struct Op* op)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) const struct Path* op_to_second_path(const struct Op* op)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) void op_to_human_readable(char* dest, int size, struct Op* op)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) int fopen_to_flags(BORROWED const char* fopentype)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) void stat_result_from_stat(struct StatResult* stat_result_buf,
                                                                 struct stat* stat_buf)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) void
stat_result_from_statx(struct StatResult* stat_result_buf, struct statx* statx_buf)
    __attribute__((nonnull));

__attribute__((visibility("hidden"))) void copy_rusage(struct my_rusage* dst, struct rusage* src)
    __attribute__((nonnull));
