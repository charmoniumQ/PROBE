#pragma once

#define _GNU_SOURCE

#include "../include/libprobe/prov_ops.h"
#include "util.h"

__attribute__((visibility("hidden")))
struct Path create_path_lazy(int dirfd, BORROWED const char* path, int flags);

__attribute__((visibility("hidden")))
void path_to_id_string(const struct Path* path, BORROWED char* string);

__attribute__((visibility("hidden")))
void do_init_ops(bool was_epoch_initted);

__attribute__((visibility("hidden")))
const struct Path* op_to_path(const struct Op* op);

__attribute__((visibility("hidden")))
const struct Path* op_to_second_path(const struct Op* op);

__attribute__((visibility("hidden")))
void op_to_human_readable(char* dest, int size, struct Op* op);
