/* Definition moved to prov_buffer.c because we need to access thread_local_arena */
/* struct InitProcessOp init_current_process() { ... } */

static int path_to_string(struct Path path, char* buffer, int buffer_length) {
    /* CHECK_SNPRINTF(
        buffer,
        PATH_MAX * 2,
        "%d %s -> (%ld, %ld, %ld)",
        path.dirfd_minus_at_fdcwd + AT_FDCWD,
        path.path,
        path.device_major,
        path.device_minor,
        path.inode); */
    return CHECK_SNPRINTF(
        buffer,
        buffer_length,
        "%d %s",
        path.dirfd_minus_at_fdcwd + AT_FDCWD,
        path.path);
}

static struct InitThreadOp init_current_thread() {
    struct InitThreadOp ret = {
        .process_id = get_process_id(),
        .process_birth_time = get_process_birth_time(),
        .exec_epoch = get_exec_epoch(),
        .sams_thread_id = get_sams_thread_id(),
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
        case chown_op_code: free_path(op.data.chown.path); break;
        case chmod_op_code: free_path(op.data.chmod.path); break;
        case read_link_op_code:
            free_path(op.data.read_link.path);
            FREE((char*) op.data.read_link.resolved);
            break;
        default:
    }
}
*/

static struct Path op_to_path(struct Op op) {
    switch (op.op_code) {
        case open_op_code: return op.data.open.path;
        case chdir_op_code: return op.data.chdir.path;
        case exec_op_code: return op.data.exec.path;
        case access_op_code: return op.data.access.path;
        case stat_op_code: return op.data.stat.path;
        case chown_op_code: return op.data.chown.path;
        case chmod_op_code: return op.data.chmod.path;
        case read_link_op_code: return op.data.read_link.path;
        default:
            return null_path;
    }
}

static BORROWED const char* op_code_to_string(enum OpCode op_code) {
    switch (op_code) {
        case init_process_op_code: return "init_process";
        case init_thread_op_code: return "init_thread";
        case open_op_code: return "open";
        case close_op_code: return "close";
        case clone_op_code: return "clone";
        case chdir_op_code: return "chdir";
        case exec_op_code: return "exec";
        case exit_op_code: return "exit";
        case access_op_code: return "access";
        case stat_op_code: return "stat";
        case chown_op_code: return "chown";
        case chmod_op_code: return "chmod";
        case read_link_op_code: return "read_link";
        default:
            ASSERTF(op_code <= FIRST_OP_CODE || op_code >= LAST_OP_CODE, "Not a valid op_code: %d", op_code);
            NOT_IMPLEMENTED("op_code %d is valid, but not handled", op_code);
    }
}

static void op_to_human_readable(char* dest, int size, struct Op op) {
    const char* op_str = op_code_to_string(op.op_code);
    strncpy(dest, op_str, size);
    size -= strlen(op_str);
    dest += strlen(op_str);
    dest[0] = ' ';
    dest++;
    size--;
    struct Path path = op_to_path(op);
    if (path.inode != null_path.inode) {
        int path_size = path_to_string(path, dest, size);
        dest += path_size;
        size -= path_size;
    }
    if (op.op_code == close_op_code) {
        int fd_size = CHECK_SNPRINTF(dest, size, "%d", op.data.close.low_fd);
        dest += fd_size;
        size -= fd_size;
    }
}

/* This is not needed since we switched to Arena allocation */
/*
static void write_op_binary(int fd, struct Op op) {
    EXPECT( > 0, write(fd, (void*) &op, sizeof(op)));
}
*/
