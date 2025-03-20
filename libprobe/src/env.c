#define _GNU_SOURCE

#include <string.h>

#include "util.h"
#include "global_state.h"

#include "env.h"

extern char** environ;

void printenv() {
    for (char** arg = environ; *arg; ++arg) {
        DEBUG("printenv: %s", *arg);
    }
}

const char* getenv_copy(const char* name) {
    /* Validate input */
    ASSERTF(name, "");
    ASSERTF(strchr(name, '=') == NULL, "");
    ASSERTF(name[0], "");
    ASSERTF(environ, "");
    size_t name_len = strlen(name);
    for (char **ep = environ; *ep; ++ep) {
        if (UNLIKELY(strncmp(name, *ep, name_len) == 0) && LIKELY((*ep)[name_len] == '=')) {
            char* val = *ep + name_len + 1;
            DEBUG("Found '%s' = '%s'", name, val);
            return val;
        }
    }
    DEBUG("'%s' not found", name);
    return NULL;
}

/*
 * TODO: Test this
 *
 * Somehow, calling glibc's getenv here doesn't work (???) for the case `bash -c 'bash -c echo'` with libprobe.
 * In that case, the following code trips up:
 *
 *     debug_getenv(__PROBE_PROCESS_BIRTH_TIME); // prints getenv: __PROBE_PROESS_BIRTH_TIME = 1000.2000 or something
 *     debug_setenv(__PROBE_PROCESS_TRACEE_PID); // prints setenv: __PROBE_PROCESS_TRACEE_PID = 2002 (formerly 2001) or something
 *     debug_getenv(__PROBE_PROCESS_BIRTH_TIME); // prints getenv: __PROBE_PROESS_BIRTH_TIME = (null)
 *
 * I'm not sure how the intervening setenv of TRACEE PID is affecting the value of BIRTH TIME.
 *
 * Somehow, when I re-implemented getenv/setenv here, the bug is absent. Wtf?
 * At least this works.
 *
 * I think it has something to do with libc's assumptions about library loading
 *
 */


char* const* update_env_with_probe_vars(char* const* user_env, size_t* updated_env_size) {
    /* Define env vars we care about */
    const char* probe_vars[] = {
        proc_root_env_var,
        exec_epoch_env_var,
        pid_env_var,
        probe_dir_env_var,
        /* TODO: include LD_PRELOAD, while noting LD_PRELOAD could have been changed by the user. */
    };
    char exec_epoch_str[UNSIGNED_INT_STRING_SIZE];
    CHECK_SNPRINTF(exec_epoch_str, UNSIGNED_INT_STRING_SIZE, "%d", get_exec_epoch());
    char pid_str[UNSIGNED_INT_STRING_SIZE];
    CHECK_SNPRINTF(pid_str, UNSIGNED_INT_STRING_SIZE, "%d", get_pid());
    const char* probe_vals[] = {
        "0",
        exec_epoch_str,
        pid_str,
        get_probe_dir(),
    };
    const size_t probe_var_count = sizeof(probe_vars) / sizeof(char*);

    /* Precompute some shiz */
    size_t probe_var_lengths[10] = { 0 };
    for (size_t i = 0; i < probe_var_count; ++i) {
        probe_var_lengths[i] = strlen(probe_vars[i]);
    }
    char* probe_entries[10] = { NULL };
    for (size_t i = 0; i < probe_var_count; ++i) {
        size_t probe_val_length = strlen(probe_vals[i]);
        probe_entries[i] = malloc(probe_var_lengths[i] + 1 + probe_val_length + 1);
        memcpy(probe_entries[i], probe_vars[i], probe_var_lengths[i]);
        probe_entries[i][probe_var_lengths[i]] = '=';
        memcpy(probe_entries[i] + probe_var_lengths[i] + 1, probe_vals[i], probe_val_length);
        probe_entries[i][probe_var_lengths[i] + 1 + probe_val_length] = '\0';
        DEBUG("Exporting %s", probe_entries[i]);
    }

    /* Compute user's size */
    size_t user_env_size = 0;
    for (char* const* arg = user_env; *arg; ++arg) {
        ++user_env_size;
    }

    /* Allocate a new env, based on the user's requested env, with our probe vars */
    char** updated_env = malloc((user_env_size + probe_var_count + 1) * sizeof(char*));
    if (!updated_env) {
        ERROR("Out of mem");
    }

    /* Copy user's env to new env
     * Clear out existence of probe_vars, if they happen to exist in the user's requested env.
     * */
    *updated_env_size = 0;
    for (char* const* ep = user_env; *ep; ++ep) {
        bool is_probe_var = false;
        for (size_t i = 0; i < probe_var_count; ++i) {
            if (memcmp(*ep, probe_vars[i], probe_var_lengths[i]) == 0 && (*ep)[probe_var_lengths[i]] == '=') {
                is_probe_var = true;
                break;
            }
        }
        if (!is_probe_var) {
            updated_env[*updated_env_size] = *ep;
            (*updated_env_size)++;
        }
    }

    /*
     * Now add our _desired_ versions of the probe vars we care about.
     */
    for (size_t i = 0; i < probe_var_count; ++i) {
        updated_env[*updated_env_size] = probe_entries[i];
        (*updated_env_size)++;
    }

    /* Top it off with a NULL */
    updated_env[*updated_env_size] = NULL;

    return updated_env;
}
