__attribute__ ((constructor)) void setup_libprov() {
    setup_function_pointers();
}

static char* const __prov_log_dir_envvar = "PROV_LOG_DIR";
static char* const __default_prov_log_dir = ".prov";
static char* __prov_log_dir = NULL;
static BORROWED char* get_prov_log_dir() {
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
                    // Free-ing counts as modifying
                    free((char*) cur_cell->ops[i].path.raw_path);
                }
                struct __ProvLogCell* old_cur_cell = cur_cell;
                cur_cell = cur_cell->next;
                free(old_cur_cell);
            }
            /*
             * Do the allocation somewhat proactively here, because we are already stopped to do a big task.
             * This allocation is mirrored by free in this function, the next time it is invoked.
             * I guess the last one never gets freed... Whatever.
             * */
            EXPECT(, __prov_log_head = __prov_log_tail = malloc(sizeof(struct __ProvLogCell)));
            __prov_log_head->next = NULL;
            EXPECT(== 0, o_fclose(log));
        }
        prov_log_enable();
    }
}

static OWNED char* lookup_on_path(BORROWED const char* bin_name) {
    const char* path = getenv("PATH");
    char* path_copy;
    /* This allocation is mirrored by free(path_copy) at the end of this function. */
    EXPECT(, path_copy = strdup(path));
    char candidate_file[PATH_MAX] = {0};
    char* path_entry = strtok(path_copy, ":");
    while (path_entry != NULL) {
        EXPECT(< PATH_MAX, snprintf(candidate_file, PATH_MAX, "%s/%s", path_entry, bin_name));
        if (o_access(candidate_file, X_OK)) {
            char* return_val;
            /* This allocation is freed by the user, since the return value is OWNED. */
            EXPECT(, return_val = strdup(candidate_file));
            free(path_copy);
            return return_val;
        }
        path_entry = strtok(path_copy, ":");
    }
    free(path_copy);
    return NULL;
}

__attribute__((unused)) static OWNED char* getname(BORROWED const FILE* file) {
    int fd = EXPECT(> 0, fileno((FILE*) file));
    char dev_fd[PATH_MAX] = {0};
    EXPECT(< PATH_MAX, snprintf(dev_fd, PATH_MAX, "/dev/fd/%d", fd));
    /* This allocation is freed by user-code, since the returned pointer is OWNED. */
    char* getname_buffer = malloc(PATH_MAX);
    int length = EXPECT(> 0, o_readlink(dev_fd, getname_buffer, PATH_MAX));
    getname_buffer[length] = '\0';
    return getname_buffer;
}
