static bool lookup_on_path(BORROWED const char* bin_name) {
    const char* path_segment_start = getenv("PATH");
    size_t bin_name_length = strlen(bin_name);
    char candidate_path [PATH_MAX + 1] = {0};
    while (path_segment_start[0] != '\0') {
        size_t path_segment_length = strcspn(path_segment_start, ":\0");
        path_join(candidate_path, path_segment_length, path_segment_start, bin_name_length, bin_name);
        if (prov_log_verbose()) {
            fprintf(stderr, "lookup_on_path: trying \"%s\"\n", candidate_path);
        }
        prov_log_record(make_op(MetadataRead, AT_FDCWD, strndup(candidate_path, PATH_MAX), null_fd, null_mode));
        if (o_access(candidate_path, X_OK)) {
            if (prov_log_verbose()) {
                fprintf(stderr, "lookup_on_path: succeded for \"%s\"\n", candidate_path);
            }
            prov_log_record(make_op(Execute, AT_FDCWD, strndup(candidate_path, PATH_MAX), null_fd, null_mode));
            return true;
        }
        path_segment_start = path_segment_start + path_segment_length + 1;
    }
    return false;
}
