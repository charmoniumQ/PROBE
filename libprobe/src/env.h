#pragma once

#include "src/probe_libc.h"
#define _GNU_SOURCE

#include <stddef.h> // for size_t
struct ArenaDir;

__attribute__((visibility("hidden"))) char* _Nullable const* _Nonnull update_env_with_probe_vars(
    char* _Nullable const* _Nonnull user_env, size_t* _Nonnull updated_env_size);

/* Copy char* const argv[] into the arena.
 * If argc argument is 0, compute argc and store there (if the size actually was zero, this is no bug).
 * If argc argument is positive, assume that is the argc.
 * */
__attribute__((visibility("hidden"))) char* _Nullable const* _Nonnull arena_copy_argv(
    struct ArenaDir* _Nonnull arena_dir, char* _Nullable const* _Nonnull argv, size_t argc);

__attribute__((visibility("hidden"))) char* _Nullable const* _Nonnull arena_copy_cmdline(
    struct ArenaDir* _Nonnull arena_dir, result_sized_mem cmdline);
