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
    if (op.op_code == OpenRead || op.op_code == OpenReadWrite || op.op_code == OpenOverWrite || op.op_code == OpenWritePart || op.op_code == OpenDir) {
        assert(op.dirfd);
        assert(op.path);
        assert(op.fd);
        assert(!op.inode_triple.null);
        fd_table_associate(op.fd, op.dirfd, op.path, op.inode_triple);
    } else if (op.op_code == Close) {
        fd_table_close(op.fd);
    } else if (op.op_code == Chdir) {
        if (op.path) {
            assert(op.fd == null_fd);
            fd_table_close(AT_FDCWD);
            fd_table_associate(AT_FDCWD, AT_FDCWD, op.path, op.inode_triple);
        } else {
            assert(op.fd > 0);
            fd_table_close(AT_FDCWD);
            fd_table_dup(op.fd, AT_FDCWD);
        }
    }
}

static char* const __prov_log_dir_envvar = "PROV_LOG_DIR";
static int __prov_log_dirfd = 0;

static void prov_log_save() {
    if (__prov_log_head != NULL && __prov_log_head->capacity != 0) {
        prov_log_disable();
        {
            if (__prov_log_dirfd == 0) {
	        char* relative_prov_log_dir = getenv(__prov_log_dir_envvar);
	        if (relative_prov_log_dir == NULL) {
	          relative_prov_log_dir = ".prov";
	        }
                struct stat stat_buf;
                int stat_ret = o_fstatat(AT_FDCWD, relative_prov_log_dir, &stat_buf, 0);
                if (stat_ret != 0) {
                    EXPECT(== 0, o_mkdir(relative_prov_log_dir, 0755));
                } else {
                    if ((stat_buf.st_mode & S_IFMT) != S_IFDIR) {
                        fprintf(stderr, "%s already exists but is not a directory\n", relative_prov_log_dir);
                        abort();
                    }
                }
	        __prov_log_dirfd = EXPECT(!= -1, o_openat(AT_FDCWD, relative_prov_log_dir, O_RDONLY | O_DIRECTORY));
		char absolute_prov_log_dir [PATH_MAX + 1] = {0};
	        EXPECT_NONNULL(o_realpath(relative_prov_log_dir, absolute_prov_log_dir));
	        /* Setenv, so child processes will be using the same prov log dir, even if they change directories. */
	        setenv(__prov_log_dir_envvar, absolute_prov_log_dir, true);

            }
            char log_name [PATH_MAX + 1] = {0};
            struct timespec ts;
            EXPECT(> 0, timespec_get(&ts, TIME_UTC));
            CHECK_SNPRINTF(
                   log_name,
                   PATH_MAX,
                   "prov.time-%ld.%ld.pid-%d.tid-%d",
		   ts.tv_sec, ts.tv_nsec, getpid(), my_gettid()
            );
	    int log_fd = EXPECT(!= -1, o_openat(__prov_log_dirfd, log_name, O_WRONLY | O_CREAT | O_APPEND));
            if (prov_log_verbose()) {
                char absolute_prov_log_dir [PATH_MAX + 1] = {0};
                char proc_self_fd [PATH_MAX + 1] = {0};
                CHECK_SNPRINTF(proc_self_fd, PATH_MAX + 1, "/proc/self/fd/%d", __prov_log_dirfd);
                EXPECT_NONNULL(o_realpath(proc_self_fd, absolute_prov_log_dir));
                fprintf(stderr, "prov_log_save: dirfd=%d, dir=\"%s\"; fname=\"%s\"; fd=%d\n", __prov_log_dirfd, absolute_prov_log_dir, log_name, log_fd);
	    }
            while (__prov_log_head != NULL) {
                for (size_t i = 0; i < __prov_log_head->capacity; ++i) {
                    write_op(log_fd, __prov_log_head->ops[i]);
                    if (__prov_log_head->ops[i].path) {
                        // Free-ing counts as modifying, so we must cast away the const.
                        free((char*) EXPECT_NONNULL(__prov_log_head->ops[i].path));
                    }
                    __prov_log_head->ops[i].path = NULL;
                }
                struct __ProvLogCell* old_head = __prov_log_head;
                __prov_log_head = __prov_log_head->next;
                free(old_head);
            }
	    __prov_log_head = __prov_log_tail = NULL;
            EXPECT(== 0, o_close(log_fd));
        }
        prov_log_enable();
    }
}
