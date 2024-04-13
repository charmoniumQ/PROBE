__attribute__ ((constructor)) void setup_libprov() {
    setup_function_pointers();
}

static char* const libprov_dir_var = "LIBPROV_DIR";
static char* const default_libprov_dir = ".prov";
static char* cached_libprov_dir = NULL;
static char* get_libprov_dir() {
    if (cached_libprov_dir == NULL) {
        cached_libprov_dir = getenv(libprov_dir_var);
        if (cached_libprov_dir == NULL) {
            cached_libprov_dir = default_libprov_dir;
        }
        assert(cached_libprov_dir);
        fprintf(stderr, "Using %s\n", cached_libprov_dir);
    }
    return cached_libprov_dir;
}

static FILE* get_prov_log_file() {
    if (log == NULL) {
        char* libprov_dir = get_libprov_dir();
        disable_log = true;
        struct statx prov_dir_statx;
        int prov_dir_statx_ret = o_statx(AT_FDCWD, libprov_dir, 0, STATX_TYPE, &prov_dir_statx);
        if (prov_dir_statx_ret != 0) {
            EXPECT(== 0, o_mkdir(libprov_dir, 0755));
        } else {
            if ((prov_dir_statx.stx_mode & S_IFMT) != S_IFDIR) {
                fprintf(stderr, "%s already exists but is not a directory\n", libprov_dir);
                abort();
            }
        }
        char log_name [PATH_MAX];
        struct timespec ts;
        EXPECT(> 0, timespec_get(&ts, TIME_UTC));
        EXPECT(> 0, snprintf(
            log_name,
            PATH_MAX,
            "%s/prov.pid-%d.tid-%d.sec-%ld.nsec-%ld",
            libprov_dir, getpid(), gettid(), ts.tv_sec, ts.tv_nsec
        ));
        log = o_fopen(log_name, "a");
        EXPECT(== 0, log == NULL);
        setbuf(log, NULL);
        disable_log = false;
    }
    return log;
}

static void save_prov_log() {
    EXPECT(== 0, fflush(log));
    EXPECT(== 0, o_fclose(log));
    log = NULL;
    get_prov_log_file();
}

/*
static char* getname(const FILE* file) {
    int fd = EXPECT(> 0, fileno(file));
    char dev_fd[PATH_MAX] = {0};
    EXPECT(< PATH_MAX, snprintf(dev_fd, PATH_MAX, "/dev/fd/%d", fd));
    int length = EXPECT(> 0, o_readlink(dev_fd, getname_buffer, PATH_MAX));
    getname_buffer[length] = '\0';
    return getname_buffer;
}
*/
