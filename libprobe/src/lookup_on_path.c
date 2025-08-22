#define _GNU_SOURCE

#include "lookup_on_path.h"

#include <fcntl.h>   // for AT_FDCWD
#include <stdbool.h> // for bool, false, true
#include <stddef.h>  // for size_t
#include <unistd.h>  // for X_OK

#include "../generated/libc_hooks.h" // for client_faccessat
#include "debug_logging.h"           // for DEBUG
#include "env.h"                     // for getenv_copy
#include "global_state.h"            // for get_default_path
#include "probe_libc.h"              // for probe_libc_strlen
#include "util.h"                    // for BORROWED, path_join

bool lookup_on_path(BORROWED const char* bin_name, BORROWED char* bin_path) {
    size_t bin_name_length = probe_libc_strlen(bin_name);
    const char* env_path = getenv_copy("PATH");

    /*
     * If this variable isn't defined, the path list defaults
     * to a list that includes the directories returned by
     * confstr(_CS_PATH) (which typically returns the value
     * "/bin:/usr/bin") and possibly also the current working directory;
     * see VERSIONS for further details.
     *
     * -- https://man7.org/linux/man-pages/man3/exec.3.html
    */
    const char* path = env_path ? env_path : get_default_path();

    DEBUG("Looking for \"%s\" on $PATH=\"%.50s...\"", bin_name, path);
    while (*path != '\0') {
        const char* part = path;
        size_t size = 0;
        for (; *path != '\0' && *path != ':'; ++path, ++size)
            ;
        if (size > 0) {
            path_join(bin_path, size, part, bin_name_length, bin_name);
            int access_ret = client_faccessat(AT_FDCWD, bin_path, X_OK, 0);
            if (access_ret == 0) {
                DEBUG("Found \"%s\"", bin_path);
                return true;
            }
        }
        path++;
    }
    DEBUG("None found");
    return false;
}
