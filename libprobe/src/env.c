#define _GNU_SOURCE

#include <limits.h>  // IWYU pragma: keep for PATH_MAX
#include <stdbool.h> // for bool, false, true
#include <stdlib.h>  // for malloc
// IWYU pragma: no_include "linux/limits.h"  for PATH_MAX

#include "../generated/bindings.h" // for FixedPath, LD_PRELOAD_VAR, PROBE_...
#include "arena.h"                 // for arena_calloc
#include "debug_logging.h"         // for DEBUG, ASSERTF, EXPECT_NONNULL
#include "global_state.h"          // for get_libprobe_path, get_probe_dir
#include "probe_libc.h"            // for probe_libc_...

#include "env.h"

bool search_on_colon_separated_path(const char* path, const char* needle, size_t needle_len) {
    while (*path != '\0') {
        const char* part = path;
        size_t size = 0;
        for (; *path != '\0' && *path != ':'; ++path, ++size)
            ;
        /* DEBUG("\"%s\"[:%ld] == \"%s\"[:%ld]", part, size, needle, needle_len); */
        if (size > 0 && size == needle_len && probe_libc_memcmp(part, needle, needle_len) == 0) {
            return true;
        }
        if (*path == '\0')
            break;
        path++;
    }
    return false;
}

#define LD_PRELOAD_EQ LD_PRELOAD_VAR "="
#define PROBE_DIR_EQ PROBE_DIR_VAR "="

char* const* update_env_with_probe_vars(char* const* env, size_t* new_env_size) {
    *new_env_size = 0;
    for (char* const* env_pair = env; *env_pair != NULL; ++env_pair) {
        /* DEBUG("env[%ld] = \"%s\"", *new_env_size, env[*new_env_size]); */
        ++*new_env_size;
    }

    char** new_env = EXPECT_NONNULL(malloc((*new_env_size + 3) * sizeof(char*)));
    probe_libc_memcpy((void*)new_env, env, (*new_env_size + 1) * sizeof(char*));

    const struct FixedPath* libprobe_path = get_libprobe_path();
    const struct FixedPath* probe_dir = get_probe_dir();

    bool found_ld_preload = false;
    bool found_probe_dir = false;

    /*
     * Note that sizeof("abc") == 4, because it includes the '\0' byte.
     * Thereore, when dealing with LD_PRELOAD_EQ which includes the '=' byte, we look at the first sizeof(LD_PRELOAD_VAR) bytes, which includes a '\0' byte.
     * */

    for (size_t idx = 0; idx < *new_env_size; ++idx) {
        /* DEBUG("new_env[%ld] = \"%s\"", idx, new_env[idx]); */
        if (probe_libc_memcmp(new_env[idx], LD_PRELOAD_EQ, sizeof(LD_PRELOAD_VAR)) == 0) {
            DEBUG("Found %s", new_env[idx]);
            found_ld_preload = true;
            const char* env_val = &new_env[idx][sizeof(LD_PRELOAD_VAR)];
            size_t env_val_len = probe_libc_strnlen(env_val, PATH_MAX * 100);
            if (!search_on_colon_separated_path(env_val, libprobe_path->bytes,
                                                libprobe_path->len)) {
                DEBUG("Could not find \"%s\" on LD_PRELOAD", libprobe_path->bytes);
                new_env[idx] =
                    malloc(sizeof(LD_PRELOAD_VAR) + libprobe_path->len + 1 + env_val_len);
                probe_libc_memcpy(&new_env[idx][0], LD_PRELOAD_EQ, sizeof(LD_PRELOAD_VAR));
                probe_libc_memcpy(&new_env[idx][sizeof(LD_PRELOAD_VAR)], libprobe_path->bytes,
                                  libprobe_path->len);
                probe_libc_memcpy(&new_env[idx][sizeof(LD_PRELOAD_VAR) + 1], ":", 1);
                probe_libc_memcpy(&new_env[idx][sizeof(LD_PRELOAD_VAR) + 1 + libprobe_path->len],
                                  env_val, env_val_len + 1);
                ASSERTF(
                    new_env[idx][sizeof(LD_PRELOAD_VAR) + 1 + libprobe_path->len + env_val_len] ==
                        '\0',
                    "");
                DEBUG("Changing %s to %s", env[idx], new_env[idx]);
            }
        } else if (probe_libc_memcmp(new_env[idx], PROBE_DIR_EQ, sizeof(PROBE_DIR_VAR)) == 0) {
            DEBUG("Found %s", new_env[idx]);
            found_probe_dir = true;
            if (probe_libc_memcmp(&new_env[idx][sizeof(PROBE_DIR_VAR)], probe_dir->bytes,
                                  probe_dir->len)) {
                DEBUG("PROBE_DIR is not equal to \"%s\"", probe_dir->bytes);
                new_env[idx] = malloc(sizeof(PROBE_DIR_VAR) + probe_dir->len + 1);
                probe_libc_memcpy(&new_env[idx][0], PROBE_DIR_EQ, sizeof(PROBE_DIR_VAR));
                probe_libc_memcpy(&new_env[idx][sizeof(PROBE_DIR_VAR)], probe_dir->bytes,
                                  probe_dir->len + 1);
                ASSERTF(new_env[idx][sizeof(PROBE_DIR_VAR) + probe_dir->len] == '\0', "");
                DEBUG("Changing %s to %s", env[idx], new_env[idx]);
            }
        }
    }

    if (!found_ld_preload) {
        new_env[*new_env_size] = malloc(sizeof(LD_PRELOAD_VAR) + libprobe_path->len + 1);
        probe_libc_memcpy(new_env[*new_env_size], LD_PRELOAD_EQ, sizeof(LD_PRELOAD_VAR));
        probe_libc_memcpy(new_env[*new_env_size] + sizeof(LD_PRELOAD_VAR), libprobe_path->bytes,
                          libprobe_path->len + 1);
        ASSERTF(new_env[*new_env_size][sizeof(LD_PRELOAD_VAR) + libprobe_path->len] == '\0', "");
        DEBUG("Appending %s", new_env[*new_env_size]);
        ++*new_env_size;
    }
    if (!found_probe_dir) {
        new_env[*new_env_size] = malloc(sizeof(PROBE_DIR_VAR) + probe_dir->len + 1);
        probe_libc_memcpy(new_env[*new_env_size], PROBE_DIR_EQ, sizeof(PROBE_DIR_VAR));
        probe_libc_memcpy(new_env[*new_env_size] + sizeof(PROBE_DIR_VAR), probe_dir->bytes,
                          probe_dir->len + 1);
        ASSERTF(new_env[*new_env_size][sizeof(PROBE_DIR_VAR) + probe_dir->len] == '\0', "");
        DEBUG("Appending %s", new_env[*new_env_size]);
        ++*new_env_size;
    }

    new_env[*new_env_size] = NULL;

    return new_env;
}

// getconf -a | grep ARG_MAX
#define ARG_MAX 2505728

char* const* arena_copy_argv(struct ArenaDir* arena_dir, char* const* argv, size_t argc) {
    if (argc == 0) {
        /* Compute argc and store in argc */
        for (char* const* argv_p = argv; *argv_p; ++argv_p) {
            ++argc;
        }
    }

    char** argv_copy = arena_calloc(arena_dir, argc + 1, sizeof(char*));

    for (size_t i = 0; i < argc; ++i) {
        size_t length = probe_libc_strnlen(argv[i], ARG_MAX);
        argv_copy[i] = arena_calloc(arena_dir, length + 1, sizeof(char));
        probe_libc_memcpy(argv_copy[i], argv[i], length + 1);
        ASSERTF(!argv_copy[i][length], "");
    }

    ASSERTF(!argv[argc], "");
    argv_copy[argc] = NULL;

    return argv_copy;
}

char* const* arena_copy_cmdline(struct ArenaDir* arena_dir, result_sized_mem cmdline) {
    size_t argc = probe_libc_memcount(cmdline.value, cmdline.size, '\0');

    char** argv_copy = arena_calloc(arena_dir, argc + 1, sizeof(char*));

    const char* ptr = cmdline.value;
    for (size_t i = 0; i < argc; ++i) {
        size_t length = probe_libc_strnlen(ptr, cmdline.size);
        argv_copy[i] = arena_calloc(arena_dir, length + 1, sizeof(char));
        probe_libc_memcpy(argv_copy[i], ptr, length + 1);
        ASSERTF(!argv_copy[i][length], "");
        ptr += length;
    }

    ASSERTF(!*ptr, "");
    argv_copy[argc] = NULL;

    return argv_copy;
}
