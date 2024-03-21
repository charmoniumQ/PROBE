__attribute__ ((constructor)) void setup_libprov() {
    setup_function_pointers();
}

#define PROV_DIR ".prov"

static FILE* get_prov_log_file() {
    if (log == NULL) {
        struct statx prov_dir_statx;
        int prov_dir_statx_ret = _o_statx(AT_FDCWD, PROV_DIR, 0, STATX_TYPE, &prov_dir_statx);
        if (prov_dir_statx_ret != 0) {
            EXPECT(== 0, _o_mkdir(PROV_DIR, 0755));
        } else {
            if ((prov_dir_statx.stx_mode & S_IFMT) != S_IFDIR) {
                fprintf(stderr, "%s already exists but is not a directory\n", PROV_DIR);
                abort();
            }
        }
        char log_name [PATH_MAX];
        struct timespec ts;
        EXPECT(> 0, timespec_get(&ts, TIME_UTC));
        EXPECT(> 0, snprintf(
            log_name,
            PATH_MAX,
            ".prov/prov.pid-%d.tid-%d.sec-%ld.nsec-%ld",
            getpid(), gettid(), ts.tv_sec, ts.tv_nsec
        ));
        log = _o_fopen(log_name, "a");
        EXPECT(== 0, log == NULL);
        setbuf(log, NULL);
    }
    return log;
}
