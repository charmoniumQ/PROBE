static bool lookup_on_path(BORROWED const char* bin_name, BORROWED char* bin_path) {
    const char* path_segment_start = getenv("PATH");
    size_t bin_name_length = strlen(bin_name);
    while (path_segment_start[0] != '\0') {
        size_t path_segment_length = strcspn(path_segment_start, ":\0");
        path_join(bin_path, path_segment_length, path_segment_start, bin_name_length, bin_name);
        struct Op op = {
            access_op_code,
            {.access = {create_path_lazy(0, bin_path), 0, 0, 0}},
            {0},
        };
        prov_log_try(op);
        int access_ret = wrapped_access(bin_path, X_OK);
        if (access_ret == 0) {
            prov_log_record(op);
            return true;
        } else {
            op.data.access.ferrno = errno;
            prov_log_record(op);
        }
        path_segment_start = path_segment_start + path_segment_length + 1;
    }
    return false;
}
