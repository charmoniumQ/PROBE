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

static __thread bool __prov_log_disable = false;

static void prov_log_disable() { __prov_log_disable = true; }
static void prov_log_enable () { __prov_log_disable = false; }
static bool prov_log_is_enabled () { return !__prov_log_disable; }

#define __prov_log_cell_size (10 * 1024)
struct __ProvLogCell {
    size_t capacity;
    struct Op ops[__prov_log_cell_size];
    struct __ProvLogCell* next;
};

static __thread struct __ProvLogCell* __prov_log_tail = NULL;
static __thread struct __ProvLogCell* __prov_log_head = NULL;

static void prov_log_record(struct Op op) {
    if (__prov_log_tail == NULL) {
        /* First time! Allocate new buffer */
        assert(__prov_log_head == NULL);
        /* This allocation is mirrored by a free in prov_log_save. */
        EXPECT(, __prov_log_head = __prov_log_tail = malloc(sizeof(struct __ProvLogCell)));
        __prov_log_head->capacity = 0;
        __prov_log_head->next = NULL;
    }
    assert(__prov_log_tail);
    assert(__prov_log_tail->capacity <= __prov_log_cell_size);
    if (__prov_log_tail->capacity == __prov_log_cell_size) {
        /* Not first time, but old one is full */
        struct __ProvLogCell* old_tail = __prov_log_tail;
        /* This allocation is mirrored by a free in prov_log_save. */
        EXPECT(, __prov_log_tail = malloc(sizeof(struct __ProvLogCell)));
        __prov_log_tail->next = NULL;
        __prov_log_tail->capacity = 0;
        old_tail->next = __prov_log_tail;
    }
    __prov_log_tail->ops[__prov_log_tail->capacity] = op;
    //fprintf_op(stderr, op);
    ++__prov_log_tail->capacity;
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
            char log_name [PATH_MAX + 1] = {0};
            struct timespec ts;
            EXPECT(> 0, timespec_get(&ts, TIME_UTC));
            CHECK_SNPRINTF(
                   log_name,
                   PATH_MAX,
                   "%s/prov.pid-%d.tid-%d.sec-%ld.nsec-%ld",
                   prov_log_dir, getpid(), gettid(), ts.tv_sec, ts.tv_nsec
            );
            FILE* log;
            EXPECT(, log = o_fopen(log_name, "w"));
            struct __ProvLogCell* cur_cell = __prov_log_head;
            while (cur_cell != NULL) {
                for (size_t i = 0; i < cur_cell->capacity; ++i) {
                    fprintf_op(log, cur_cell->ops[i]);
                    // Free-ing counts as modifying
                    free((char*) cur_cell->ops[i].owned_normalized_path);
                    cur_cell->ops[i].owned_normalized_path = NULL;
                }
                {
                    struct __ProvLogCell* old_cur_cell = cur_cell;
                    cur_cell = cur_cell->next;
                    free(old_cur_cell);
                }
            }
            EXPECT(== 0, o_fclose(log));
        }
        prov_log_enable();
    }
}
