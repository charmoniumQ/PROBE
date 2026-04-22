#pragma once
#define _GNU_SOURCE

#include "../generated/headers.h"
#include "probe_libc.h" // for result_sized_mem
#include <stddef.h>     // for size_t

struct ArenaDir;

__attribute__((visibility("hidden"))) StringArray update_env_with_probe_vars(
    char const* _Nullable const* _Nonnull user_env, size_t* _Nonnull updated_env_size);
