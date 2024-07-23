static struct Path create_path_lazy(int dirfd, BORROWED const char* path, int flags) {
    if (likely(prov_log_is_enabled())) {
        struct Path ret = {
            dirfd - AT_FDCWD,
            (path != NULL ? EXPECT_NONNULL(arena_strndup(get_data_arena(), path, PATH_MAX)) : NULL),
            -1,
            -1,
            -1,
            {0},
            {0},
            false,
            true,
        };

        /*
         * If path is empty string, AT_EMPTY_PATH should probably be set.
         * I can't think of a counterexample that isn't some kind of error.
         * However, some functions permit passing NULL.
         *
         * Then again, this could happen in the tracee's code too...
         * TODO: Remove this once I debug myself.
         * */
        assert(path == NULL || path[0] != '\0' || flags & AT_EMPTY_PATH);

        /*
         * if path == NULL, then the target is the dir specified by dirfd.
         * */
        prov_log_disable();
        struct statx statx_buf;
        int stat_ret = unwrapped_statx(dirfd, path, flags, STATX_INO | STATX_MTIME | STATX_CTIME, &statx_buf);
        prov_log_enable();
        if (stat_ret == 0) {
            ret.device_major = statx_buf.stx_dev_major;
            ret.device_minor = statx_buf.stx_dev_minor;
            ret.inode = statx_buf.stx_ino;
            ret.mtime = statx_buf.stx_mtime;
            ret.ctime = statx_buf.stx_ctime;
            ret.stat_valid = true;
        }
        return ret;
    } else {
        DEBUG("prov log not enabled");
        return null_path;
    }
}

struct InitProcessOp init_current_process() {
    struct InitProcessOp ret = {
        .pid = getpid(),
    };
    return ret;
}

struct InitExecEpochOp init_current_exec_epoch() {
    extern char *__progname;
    struct InitExecEpochOp ret = {
        .epoch = get_exec_epoch(),
        .program_name = arena_strndup(get_data_arena(), __progname, PATH_MAX),
    };
    return ret;
}

static struct InitThreadOp init_current_thread() {
    struct InitThreadOp ret = {
        .tid = my_gettid(),
    };
    return ret;
}

static int fopen_to_flags(BORROWED const char* fopentype) {
    /* Table from fopen to open is documented here:
     * https://www.man7.org/linux/man-pages/man3/fopen.3.html
     **/
    bool plus = fopentype[1] == '+' || (fopentype[1] != '\0' && fopentype[2] == '+');
    if (false) {
    } else if (fopentype[0] == 'r' && !plus) {
        return O_RDONLY;
    } else if (fopentype[0] == 'r' && plus) {
        return O_RDWR;
    } else if (fopentype[0] == 'w' && !plus) {
        return O_WRONLY | O_CREAT | O_TRUNC;
    } else if (fopentype[0] == 'w' && plus) {
        return O_RDWR | O_CREAT | O_TRUNC;
    } else if (fopentype[0] == 'a' && !plus) {
        return O_WRONLY | O_CREAT | O_APPEND;
    } else if (fopentype[0] == 'a' && plus) {
        return O_RDWR | O_CREAT | O_APPEND;
    } else {
        NOT_IMPLEMENTED("Unknown fopentype %s", fopentype);
    }
}

/*
static void free_op(struct Op op) {
    switch (op.op_code) {
        case open_op_code: free_path(op.data.open.path); break;
        case init_process_op_code: FREE(op.data.init_process.program_name); break;
        case exec_op_code: free_path(op.data.exec.path); break;
        case access_op_code: free_path(op.data.access.path); break;
        case stat_op_code: free_path(op.data.stat.path); break;
        case read_link_op_code:
            free_path(op.data.read_link.path);
            FREE((char*) op.data.read_link.resolved);
            break;
        default:
    }
}
*/

#ifndef NDEBUG
static const struct Path* op_to_path(struct Op* op) {
    switch (op->op_code) {
        case open_op_code: return &op->data.open.path;
        case chdir_op_code: return &op->data.chdir.path;
        case exec_op_code: return &op->data.exec.path;
        case access_op_code: return &op->data.access.path;
        case stat_op_code: return &op->data.stat.path;
        case update_metadata_op_code: return &op->data.update_metadata.path;
        case read_link_op_code: return &op->data.read_link.path;
        default:
            return &null_path;
    }
}
static BORROWED const char* op_code_to_string(enum OpCode op_code) {
    switch (op_code) {
        case init_process_op_code: return "init_process";
        case init_exec_epoch_op_code: return "init_exec_epoch";
        case init_thread_op_code: return "init_thread";
        case open_op_code: return "open";
        case close_op_code: return "close";
        case clone_op_code: return "clone";
        case chdir_op_code: return "chdir";
        case exec_op_code: return "exec";
        case exit_op_code: return "exit";
        case access_op_code: return "access";
        case stat_op_code: return "stat";
        case readdir_op_code: return "readdir";
        case wait_op_code: return "wait";
        case update_metadata_op_code: return "update_metadata";
        case read_link_op_code: return "readlink";
        default:
            ASSERTF(FIRST_OP_CODE < op_code && op_code < LAST_OP_CODE, "Not a valid op_code: %d", op_code);
            NOT_IMPLEMENTED("op_code %d is valid, but not handled", op_code);
    }
}
static int path_to_string(const struct Path* path, char* buffer, int buffer_length) {
    return CHECK_SNPRINTF(
        buffer,
        buffer_length,
        "dirfd=%d, path=\"%s\", stat_valid=%d, dirfd_valid=%d",
        path->dirfd_minus_at_fdcwd + AT_FDCWD,
        path->path,
        path->stat_valid,
        path->dirfd_valid
    );
}
static void op_to_human_readable(char* dest, int size, struct Op* op) {
    const char* op_str = op_code_to_string(op->op_code);
    strncpy(dest, op_str, size);
    size -= strlen(op_str);
    dest += strlen(op_str);

    dest[0] = ' ';
    dest++;
    size--;

    const struct Path* path = op_to_path(op);
    if (path->dirfd_valid) {
        int path_size = path_to_string(path, dest, size);
        dest += path_size;
        size -= path_size;
    }

    if (op->op_code == open_op_code) {
        int fd_size = CHECK_SNPRINTF(dest, size, " fd=%d", op->data.open.fd);
        dest += fd_size;
        size -= fd_size;
    }

    if (op->op_code == close_op_code) {
        int fd_size = CHECK_SNPRINTF(dest, size, " fd=%d", op->data.close.low_fd);
        dest += fd_size;
        size -= fd_size;
    }
}
#endif

void stat_to_statx(struct statx* statx_buf, struct stat* stat_buf) {
    /*
     * Sadly ChatGPT gets this wrong
     * Here's the old-fashioned documentation:
     *
     * https://www.gnu.org/software/libc/manual/html_node/Attribute-Meanings.html#index-struct-stat
     * https://www.man7.org/linux/man-pages/man2/statx.2.html
     */
    statx_buf->stx_mask = STATX_BASIC_STATS;
    statx_buf->stx_mode = stat_buf->st_mode;
    statx_buf->stx_ino = stat_buf->st_ino;
    statx_buf->stx_dev_major = major(stat_buf->st_dev);
    statx_buf->stx_dev_major = minor(stat_buf->st_dev);
    statx_buf->stx_nlink = stat_buf->st_nlink;
    statx_buf->stx_uid = stat_buf->st_uid;
    statx_buf->stx_gid = stat_buf->st_gid;
    statx_buf->stx_size = stat_buf->st_size;
    statx_buf->stx_atime.tv_sec = stat_buf->st_atim.tv_sec;
    statx_buf->stx_atime.tv_nsec = stat_buf->st_atim.tv_nsec;
    statx_buf->stx_mtime.tv_sec = stat_buf->st_mtim.tv_sec;
    statx_buf->stx_mtime.tv_nsec = stat_buf->st_mtim.tv_nsec;
    statx_buf->stx_ctime.tv_sec = stat_buf->st_ctim.tv_sec;
    statx_buf->stx_ctime.tv_nsec = stat_buf->st_ctim.tv_nsec;
    statx_buf->stx_blocks = stat_buf->st_blocks;
    statx_buf->stx_blksize = stat_buf->st_blksize;
}

void stat64_to_statx(struct statx* statx_buf, struct stat64* stat_buf) {
    statx_buf->stx_mask = STATX_BASIC_STATS;
    statx_buf->stx_mode = stat_buf->st_mode;
    statx_buf->stx_ino = stat_buf->st_ino;
    statx_buf->stx_dev_major = major(stat_buf->st_dev);
    statx_buf->stx_dev_major = minor(stat_buf->st_dev);
    statx_buf->stx_nlink = stat_buf->st_nlink;
    statx_buf->stx_uid = stat_buf->st_uid;
    statx_buf->stx_gid = stat_buf->st_gid;
    statx_buf->stx_size = stat_buf->st_size;
    statx_buf->stx_atime.tv_sec = stat_buf->st_atim.tv_sec;
    statx_buf->stx_atime.tv_nsec = stat_buf->st_atim.tv_nsec;
    statx_buf->stx_mtime.tv_sec = stat_buf->st_mtim.tv_sec;
    statx_buf->stx_mtime.tv_nsec = stat_buf->st_mtim.tv_nsec;
    statx_buf->stx_ctime.tv_sec = stat_buf->st_ctim.tv_sec;
    statx_buf->stx_ctime.tv_nsec = stat_buf->st_ctim.tv_nsec;
    statx_buf->stx_blocks = stat_buf->st_blocks;
    statx_buf->stx_blksize = stat_buf->st_blksize;
}
