#pragma once

#define _GNU_SOURCE

#include <stddef.h>
struct ArenaDir;

__attribute__((visibility("hidden")))
void printenv(void);

__attribute__((visibility("hidden")))
const char* getenv_copy(const char* name)
    __attribute__((nonnull));

__attribute__((visibility("hidden")))
char* const* update_env_with_probe_vars(char* const* user_env, size_t* updated_env_size)
    __attribute__((nonnull, returns_nonnull));

/* Copy char* const argv[] into the arena.
 * If argc argument is 0, compute argc and store there (if the size actually was zero, this is no bug).
 * If argc argument is positive, assume that is the argc.
 * */
__attribute__((visibility("hidden")))
char* const* arena_copy_argv(struct ArenaDir* arena_dir, char * const * argv, size_t* argc)
    __attribute__((nonnull, returns_nonnull));
