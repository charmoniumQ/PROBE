static bool lookup_on_path(BORROWED const char* bin_name, BORROWED char* bin_path) {
    const char* path_segment_start = getenv("PATH");
    DEBUG("looking up \"%s\" on $PATH=\"%.50s...\"", bin_name, path_segment_start);
    size_t bin_name_length = strlen(bin_name);
    while (path_segment_start[0] == ':') {
        /* TODO: Test case where PATH starts with : */
        path_segment_start++;
    }
    bool has_elements = path_segment_start == NULL || path_segment_start[0] == '\0';
    /* TODO: Use default PATH when PATH is unset */
    if (has_elements) {
        while (true) {
            size_t path_segment_length = strcspn(path_segment_start, ":\0");
            path_join(bin_path, path_segment_length, path_segment_start, bin_name_length, bin_name);
            struct Op op = {
                access_op_code,
                {.access = {create_path_lazy(AT_FDCWD, bin_path, 0), 0, 0, 0}},
                {0},
                0,
                0,
            };
            /* TODO: Test case where PATH element is relative */
            prov_log_try(op);
            int access_ret = unwrapped_faccessat(AT_FDCWD, bin_path, X_OK, 0);
            if (access_ret == 0) {
                prov_log_record(op);
                return true;
            } else {
                op.data.access.ferrno = errno;
                prov_log_record(op);
            }
            while (path_segment_start[0] == ':') {
                /* TODO: Test case where PATH segment contains empty strings, /foo/bin:::/bar/bin */
                path_segment_start++;
            }
            if (path_segment_start[0] == '\0') {
                break;
            }
        }
    }
    return false;
}
