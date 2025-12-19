#pragma once

#define _GNU_SOURCE

#include "util.h"    // for BORROWED
#include <stdbool.h> // for bool
// IWYU pragma: no_include "libprobe/prov_ops.h" for Op (ptr only), StatResult (ptr only)
// IWYU pragma: no_include "/build/libprobe/include/libprobe/prov_ops.h"

struct Op;         // IWYU pragma: keep
struct StatResult; // IWYU pragma: keep
struct my_rusage;  // IWYU pragma: keep
struct rusage;
struct stat;

__attribute__((visibility("hidden"))) struct Path2 to_path(int dirfd, const char* _Nullable filename, size_t length);

__attribute__((visibility("hidden"))) void path_to_id_string(const struct StatResult* _Nonnull stat,
                                                             BORROWED char* _Nonnull string);

__attribute__((visibility("hidden"))) OpenNumber open_numbering_new(int fd);

__attribute__((visibility("hidden"))) OpenNumber open_numbering_close(int fd);

__attribute__((visibility("hidden"))) OpenNumber open_numbering_dup(int oldfd, int newfd, OpenNumber* _Nullable closed_dest);

__attribute__((visibility("hidden"))) struct StatxTruncated my_fstat(int fd, int stat_flags);

__attribute__((visibility("hidden"))) struct StatxTruncated copy_if_necessary(int fd, int open_flags);

__attribute__((visibility("hidden"))) void do_init_ops(bool was_epoch_initted);

__attribute__((visibility("hidden"))) const struct Path* _Nonnull op_to_path(const struct Op* _Nonnull op);

__attribute__((visibility("hidden"))) const struct Path* _Nonnull op_to_second_path(const struct Op* _Nonnull op);

__attribute__((visibility("hidden"))) void op_to_human_readable(char* _Nonnull dest, int size, struct Op* _Nonnull op);

__attribute__((visibility("hidden"))) int fopen_to_flags(BORROWED const char* _Nonnull fopentype);

__attribute__((visibility("hidden"))) struct StatxTruncated stat_result_from_stat(struct stat stat_buf);

__attribute__((visibility("hidden"))) void copy_rusage(struct my_rusage* _Nonnull dst, struct rusage* _Nonnull src);
