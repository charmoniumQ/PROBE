static __thread bool __prov_log_disable = false;

static void prov_log_disable() { __prov_log_disable = true; }
static void prov_log_enable () { __prov_log_disable = false; }
static bool prov_log_is_enabled () { return !__prov_log_disable; }
static void prov_log_set_enabled (bool value) { __prov_log_disable = value; }

#define __prov_log_cell_size (10 * 1024)
struct __ProvLogCell {
    size_t capacity;
    struct Op ops[__prov_log_cell_size];
    struct __ProvLogCell* next;
};

static __thread struct __ProvLogCell* __prov_log_tail = NULL;
static __thread struct __ProvLogCell* __prov_log_head = NULL;

/*
 * Call this to indicate that the process is about to do some op.
 * The values of the op that are not known before executing the call
 * (e.g., fd for open is not known before-hand)
 * just put something random in there.
 * We promise not to read those fields in this function.
 */
static void prov_log_try(struct Op op) {
    (void) op;
}

/*
 * Call this to indicate that the process did something (successful or not).
 */
static void prov_log_record(struct Op op) {
    if (__prov_log_tail == NULL) {
        /* TODO: move this to init_thread_prov_log() */
        /* TODO: Have a fixed buffer */
        /* First time! Allocate new buffer */
        assert(__prov_log_head == NULL);
        /* This allocation is mirrored by a free in prov_log_save. */
        __prov_log_head = __prov_log_tail = EXPECT_NONNULL(malloc(sizeof(struct __ProvLogCell)));
        __prov_log_head->capacity = 0;
        __prov_log_head->next = NULL;
    }
    assert(__prov_log_tail);
    assert(__prov_log_head);
    assert(__prov_log_tail->capacity <= __prov_log_cell_size);
    if (__prov_log_tail->capacity == __prov_log_cell_size) {
        /* Not first time, but old one is full */
        struct __ProvLogCell* old_tail = __prov_log_tail;
        /* This allocation is mirrored by a free in prov_log_save. */
        __prov_log_tail = EXPECT_NONNULL(malloc(sizeof(struct __ProvLogCell)));
        __prov_log_tail->next = NULL;
        __prov_log_tail->capacity = 0;
        old_tail->next = __prov_log_tail;
    }
    __prov_log_tail->ops[__prov_log_tail->capacity] = op;

    if (prov_log_verbose()) {
        fprintf(stderr, "prov log op: ");
        write_op(STDERR_FILENO, op);
    }

    ++__prov_log_tail->capacity;

    /* TODO: Special handling of ops that affect process state */
    /* if (op.op_code == OpenRead || op.op_code == OpenReadWrite || op.op_code == OpenOverWrite || op.op_code == OpenWritePart || op.op_code == OpenDir) { */
    /*     assert(op.dirfd); */
    /*     assert(op.path); */
    /*     assert(op.fd); */
    /*     assert(!op.inode_triple.null); */
    /*     fd_table_associate(op.fd, op.dirfd, op.path, op.inode_triple); */
    /* } else if (op.op_code == Close) { */
    /*     fd_table_close(op.fd); */
    /* } else if (op.op_code == Chdir) { */
    /*     if (op.path) { */
    /*         assert(op.fd == null_fd); */
    /*         fd_table_close(AT_FDCWD); */
    /*         fd_table_associate(AT_FDCWD, AT_FDCWD, op.path, op.inode_triple); */
    /*     } else { */
    /*         assert(op.fd > 0); */
    /*         fd_table_close(AT_FDCWD); */
    /*         fd_table_dup(op.fd, AT_FDCWD); */
    /*     } */
    /* } */
}

static int __prov_log_dirfd = -1;
static void init_process_prov_log() {
    assert(__prov_log_dirfd == -1);
    static char* const __prov_log_dir_envvar = "PROV_LOG_DIR";
    char* relative_prov_log_dir = getenv(__prov_log_dir_envvar);
    if (relative_prov_log_dir == NULL) {
        relative_prov_log_dir = ".prov";
    }
    struct stat stat_buf;
    int stat_ret = o_fstatat(AT_FDCWD, relative_prov_log_dir, &stat_buf, 0);
    if (stat_ret != 0) {
        EXPECT(== 0, o_mkdir(relative_prov_log_dir, 0755));
    } else {
        ASSERTF((stat_buf.st_mode & S_IFMT) == S_IFDIR, "%s already exists but is not a directory\n", relative_prov_log_dir);
    }
    __prov_log_dirfd = EXPECT(!= -1, o_openat(AT_FDCWD, relative_prov_log_dir, O_RDONLY | O_DIRECTORY));
    char absolute_prov_log_dir [PATH_MAX + 1] = {0};
    EXPECT_NONNULL(o_realpath(relative_prov_log_dir, absolute_prov_log_dir));
    /* Setenv, so child processes will be using the same prov log dir, even if they change directories. */
    setenv(__prov_log_dir_envvar, absolute_prov_log_dir, true);
    if (prov_log_verbose()) {
        fprintf(stderr, "init_process_prov_log: %s\n", absolute_prov_log_dir);
    }
}

static int __prov_log_fd = -1;
static void init_thread_prov_log() {
    assert(__prov_log_fd == -1);
    char log_name [PATH_MAX + 1] = {0};
    struct timespec process_birth_time = get_process_birth_time();
    /* TODO: use fixed-string formatting instead of snprintf
     * Fixed-string might be faster and less error-prone.
     * Also, putting in leading zeros will help the sort.
     * */
    CHECK_SNPRINTF(
        log_name,
        PATH_MAX,
        "%d-%d-%ld-%ld-%d.prov",
        get_process_id(), get_exec_epoch(), process_birth_time.tv_sec, process_birth_time.tv_nsec, get_sams_thread_id()
    );
    /* Note that the mode is not actually set to 0777.
     * > The effective mode is modified by the process's umask in the usual way: ... mode & ~umask
     * https://www.man7.org/linux/man-pages/man2/openat.2.html
     * */
    __prov_log_fd = EXPECT(!= -1, o_openat(__prov_log_dirfd, log_name, O_WRONLY | O_CREAT, 0777));
    if (prov_log_verbose()) {
        fprintf(stderr, "init_thread_prov_log: %s\n", log_name);
    }
}

static void prov_log_term_process() {
    /* Dump all orphaned threads & close all thread prov log fds*/
    EXPECT(== 0, o_close(__prov_log_dirfd));
}

static void prov_log_save() {
    if (__prov_log_head->capacity != 0) {
        while (__prov_log_head != NULL) {
            for (size_t i = 0; i < __prov_log_head->capacity; ++i) {
                write_op(__prov_log_fd, __prov_log_head->ops[i]);
                free_op(__prov_log_head->ops[i]);
            }
            struct __ProvLogCell* old_head = __prov_log_head;
            __prov_log_head = __prov_log_head->next;
            free(old_head);
        }
        __prov_log_head = __prov_log_tail = NULL;
    }
}

static struct Path create_path_lazy(int dirfd, BORROWED const char* path) {
    if (likely(prov_log_is_enabled())) {
        return create_path(dirfd, path);
    } else {
        return null_path;
    }
}
