__attribute__ ((constructor)) void setup_libprov() {
    setup_function_pointers();
}

static char* const __prov_log_dir_envvar = "PROV_LOG_DIR";
static char* const __default_prov_log_dir = ".prov";
static char* __prov_log_dir = NULL;
static char* get_prov_log_dir() {
    if (__prov_log_dir == NULL) {
        __prov_log_dir = getenv(__prov_log_dir_envvar);
        if (__prov_log_dir == NULL) {
            __prov_log_dir = __default_prov_log_dir;
        }
        assert(__prov_log_dir);
    }
    return __prov_log_dir;
}

static void prov_log_save() {
    if (__prov_log_head != NULL && __prov_log_head->capacity != 0) {
        prov_log_disable();
        {
            char* prov_log_dir = get_prov_log_dir();
            struct statx prov_dir_statx;
            int prov_dir_statx_ret = o_statx(AT_FDCWD, prov_log_dir, 0, STATX_TYPE, &prov_dir_statx);
            if (prov_dir_statx_ret != 0) {
                EXPECT(== 0, o_mkdir(prov_log_dir, 0755));
            } else {
                if ((prov_dir_statx.stx_mode & S_IFMT) != S_IFDIR) {
                    fprintf(stderr, "%s already exists but is not a directory\n", prov_log_dir);
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
                       prov_log_dir, getpid(), gettid(), ts.tv_sec, ts.tv_nsec
            ));
            FILE* log;
            EXPECT(, log = o_fopen(log_name, "w"));
            struct __ProvLogCell* cur_cell = __prov_log_head;
            while (cur_cell != NULL) {
                for (size_t i = 0; i < cur_cell->capacity; ++i) {
                    fprintf_op(log, cur_cell->ops[i]);
                }
                cur_cell = cur_cell->next;
            }
            /* Do the allocation somewhat proactively here, because we are already stopped to do a big task. */
            EXPECT(, __prov_log_head = __prov_log_tail = malloc(sizeof(struct __ProvLogCell)));
            __prov_log_head->next = NULL;
            EXPECT(== 0, o_fclose(log));
        }
        prov_log_enable();
    }
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
