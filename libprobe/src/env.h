#pragma once

#define _GNU_SOURCE

#include <stddef.h>

__attribute__((visibility("hidden")))
void printenv(void);

__attribute__((visibility("hidden")))
const char* getenv_copy(const char* name);

__attribute__((visibility("hidden")))
char* const* update_env_with_probe_vars(char* const* user_env, size_t* updated_env_size);
