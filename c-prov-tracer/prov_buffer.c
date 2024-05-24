static _Atomic bool __prov_log_disable = false;

static void prov_log_disable() { __prov_log_disable = true; }
static void prov_log_enable () { __prov_log_disable = false; }
static bool prov_log_is_enabled () { return !__prov_log_disable; }
static void prov_log_set_enabled (bool value) { __prov_log_disable = value; }

/**
 * We hold a thread-local buffer of prov ops.
 * We will dump it when it gets too big, or at the end of the process (atexit).
 * Therefore, the process needs to have a handle to it.
 *
 * Performance note:
 * The greater op_buffer_size, the fewer times we have to hit the disk.
 * But the more memory we use.
 * I think hitting the disk isn't so bad, because some of the syscalls do that anyway
 * and modern Linux has a writethrough cache for files.
 * */
#define op_buffer_size (1024 * 64)
struct Buffer {
    struct Op ops[op_buffer_size];
    size_t used;
    int fd;
};
static __thread struct Buffer* thread_local_op_buffer;

/*
 * Process holds 1 buffer per thread in a linked list of arrays of buffers.
 *
 * Performance note:
 * The  buffer_linked_list_array_size, the more threads I can allocate before I have to allocate a new array.
 * But also the more memory this takes when we aren't using all thsoe threads.
 * */
#define buffer_linked_list_array_size (64)
struct BufferLinkedList {
    struct Buffer* buffer_array[buffer_linked_list_array_size];
    struct BufferLinkedList* next;
};
static struct BufferLinkedList head = {0};

static void __any_prov_log_save(struct Buffer* buffer) {
    for (size_t i = 0; i < buffer->used; ++i) {
        write_op_binary(buffer->fd, buffer->ops[i]);
        free_op(buffer->ops[i]);
    }
    buffer->used = 0;
}

static void prov_log_save() {
    __any_prov_log_save(thread_local_op_buffer);
}

/*
 * Call this to indicate that the process is about to do some op.
 * The values of the op that are not known before executing the call
 * (e.g., fd for open is not known before-hand)
 * just put something random in there.
 * We promise not to read those fields in this function.
 */
static void prov_log_try(struct Op op) {
    (void) op;

    if (op.op_code == clone_op_code && op.data.clone.flags & CLONE_VFORK) {
            DEBUG("I don't know if CLONE_VFORK actually works. See libc_hooks_source.c for vfork()");
    }
}

/*
 * Call this to indicate that the process did something (successful or not).
 */
static void prov_log_record(struct Op op) {
    if (prov_log_verbose()) {
        char str[PATH_MAX * 2];
        op_to_human_readable(str, PATH_MAX * 2, op);
        DEBUG("op: %s", str);
    }

    if (thread_local_op_buffer->used == op_buffer_size) {
        DEBUG("Saving buffer before continuing");
        prov_log_save();
        assert(thread_local_op_buffer->used == 0);
    }

    if (op.time.tv_sec == 0 && op.time.tv_nsec == 0) {
        EXPECT(== 0, clock_gettime(CLOCK_MONOTONIC, &op.time));
    }

    thread_local_op_buffer->ops[thread_local_op_buffer->used] = op;
    ++thread_local_op_buffer->used;

    if (op.op_code == clone_op_code) {
        DEBUG("clone: process %d, thread %d", get_process_id(), get_sams_thread_id());
    }

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
    static char* const dir_env_var = ENV_VAR_PREFIX "DIR";
    char* relative_dir = getenv(dir_env_var);
    if (relative_dir == NULL) {
        assert(is_prov_root());
        relative_dir = ".prov";
    }
    struct stat stat_buf;
    int stat_ret = o_fstatat(AT_FDCWD, relative_dir, &stat_buf, 0);
    if (stat_ret != 0) {
        EXPECT(== 0, o_mkdir(relative_dir, 0755));
    } else {
        ASSERTF((stat_buf.st_mode & S_IFMT) == S_IFDIR, "%s already exists but is not a directory\n", relative_dir);
    }
    __prov_log_dirfd = EXPECT(!= -1, o_openat(AT_FDCWD, relative_dir, O_RDONLY | O_DIRECTORY));
    char absolute_dir [PATH_MAX + 1] = {0};
    EXPECT_NONNULL(o_realpath(relative_dir, absolute_dir));
    /* Setenv, so child processes will be using the same prov log dir, even if they change directories. */
    setenv(dir_env_var, absolute_dir, true);
    DEBUG("init_process_prov_log: %s", absolute_dir);
}

static void init_thread_prov_log() {
    pid_t sams_thread_id = get_sams_thread_id();
    struct BufferLinkedList* current = &head;
    while (sams_thread_id > buffer_linked_list_array_size) {
        if (current->next == NULL) {
            current->next = EXPECT_NONNULL(calloc(1, sizeof(struct BufferLinkedList)));
            /*
             * This allocation is freed by prov_log_term_processes
             * */
        }
        current = current->next;
        sams_thread_id -= buffer_linked_list_array_size;
    }
    assert(current->buffer_array[sams_thread_id] == NULL);
    thread_local_op_buffer = current->buffer_array[sams_thread_id] = EXPECT_NONNULL(malloc(sizeof(struct Buffer)));
    thread_local_op_buffer->used = 0;

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
    thread_local_op_buffer->fd = EXPECT(!= -1, o_openat(__prov_log_dirfd, log_name, O_WRONLY | O_CREAT, 0777));
    DEBUG("init_thread_prov_log: %s", log_name);
}

static void prov_log_term_process() {
    /* Dump all orphaned threads & close all thread prov log fds*/
    struct BufferLinkedList* current = &head;
    while (current) {
        for (int i = 0; i < buffer_linked_list_array_size; ++i) {
            if (current->buffer_array[i] != NULL) {
                DEBUG("Saving process %d, thread %d", get_process_id(), i);
                __any_prov_log_save(current->buffer_array[i]);
                assert(current->buffer_array[i]->used == 0);
                o_close(current->buffer_array[i]->fd);
                FREE(current->buffer_array[i]);
                current->buffer_array[i] = NULL;
            }
        }
        struct BufferLinkedList* old_current = current;
        current = current->next;
        /* This NULL is defensive; if someone kept a pointer to current, they will not be able to follow it anywhere. */
        old_current->next = NULL;
        if (old_current != &head) {
            FREE(old_current);
        }
    }
    o_close(__prov_log_dirfd);
}

static struct Path create_path_lazy(int dirfd, BORROWED const char* path) {
    if (likely(prov_log_is_enabled())) {
        return create_path(dirfd, path);
    } else {
        return null_path;
    }
}
