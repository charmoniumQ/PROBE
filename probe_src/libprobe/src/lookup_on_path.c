#include <stdbool.h>  
#include <stdlib.h>   
#include <string.h>   
#include <stddef.h> 
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

static bool lookup_on_path(BORROWED const char* bin_name, BORROWED char* bin_path) {
    size_t bin_name_length = strlen(bin_name);
    char* env_path = getenv("PATH");

    /*
     * If this variable isn't defined, the path list defaults
     * to a list that includes the directories returned by
     * confstr(_CS_PATH) (which typically returns the value
     * "/bin:/usr/bin") and possibly also the current working directory;
     * see VERSIONS for further details.
     *
     * -- https://man7.org/linux/man-pages/man3/exec.3.html
    */
    char* path = env_path ? env_path : get_default_path();
    /* Note that strtok_r is destructive, so we will have to copy this. */
    path = strndup(path, sysconf(_SC_ARG_MAX));

    DEBUG("looking up \"%s\" on $PATH=\"%.50s...\"", bin_name, path);

    char* saveptr = NULL;
    const char *delim = ":";
    char *path_seg;
    path_seg = strtok_r(path, delim, &saveptr);
    while (path_seg) {
        path_join(bin_path, -1, path_seg, bin_name_length, bin_name);
        struct Op op = {
            access_op_code,
            {.access = {create_path_lazy(AT_FDCWD, bin_path, 0), 0, 0, 0}},
            {0},
            0,
            0,
        };
        prov_log_try(op);
        int access_ret = unwrapped_faccessat(AT_FDCWD, bin_path, X_OK, 0);
        if (access_ret == 0) {
            prov_log_record(op);
            return true;
        } else {
            op.data.access.ferrno = errno;
            prov_log_record(op);
        }
        path_seg = strtok_r(NULL, delim, &saveptr);
    }

    return false;
}
