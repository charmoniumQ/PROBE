/*
 * This file looks like C, but it is not read by the C compiler!
 * It is a place-holder for C code and is processed by gen_libprov.py and put into libprov_middle.c.
 * It re-uses C's grammar, so I get syntax highlighting and I can parse it into fragments of C syntax easily.
 * Rationale: In this part of the project, there are many repetitions of code automatically generated.
 * For example, for each function $foo, we define a wrapper function $foo that calls the original function unwrapped_$foo with the same arguments.
 * Just read libprov_middle.c.
 * I can more easily refactor how it works if I don't have to edit each individual instance.
 * gen_libprov.py reads the function signatures, and inside the function bodies, it looks for some specific variable declarations of the form: Type var_name = var_val;
 * We use GCC block-expressions to communicate blocks of code to gen_libprov.py: ({stmt0; stmt1; ...; }).
 */

/* Need these typedefs to make pycparser parse the functions. They won't be used in libprov_middle.c */
typedef void* FILE;
typedef void* DIR;
typedef void* pid_t;
typedef void* mode_t;
typedef void* __ftw_func_t;
typedef void* __ftw64_func_t;
typedef void* __nftw_func_t;
typedef void* __nftw64_func_t;
typedef void* size_t;
typedef void* ssize_t;
typedef void* off_t;
typedef void* off64_t;
typedef void* dev_t;
typedef void* uid_t;
typedef void* gid_t;
typedef void* idtype_t;
typedef void* idtype;
typedef void* id_t;
typedef void* siginfo_t;
typedef int bool;
struct stat;
struct stat64;
struct utimebuf;
typedef void* OpCode;
typedef void* fn;
typedef void* va_list;
struct utimbuf;
struct dirent;
int __type_mode_t;
typedef void* thrd_t;
typedef void* thrd_start_t;
typedef void* pthread_t;
typedef void* pthread_attr_t;

typedef int (*fn_ptr_int_void_ptr)(void*);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html */
FILE * fopen (const char *filename, const char *opentype) {
    void* pre_call = ({
        struct Op op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = fopen_to_flags(opentype),
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == NULL) {
                op.data.open.ferrno = saved_errno;
            } else {
                op.data.open.fd = fileno(ret);
            }
            prov_log_record(op);
        }
    });
}
fn fopen64 = fopen;
FILE * freopen (const char *filename, const char *opentype, FILE *stream) {
    void* pre_call = ({
        int original_fd = fileno(stream);
        struct Op open_op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = fopen_to_flags(opentype),
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        struct Op close_op = {
            close_op_code,
            {.close = {original_fd, original_fd, 0}},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(open_op);
            prov_log_try(close_op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == NULL) {
                open_op.data.open.ferrno = saved_errno;
                close_op.data.close.ferrno = saved_errno;
            } else {
                open_op.data.open.fd = fileno(ret);
            }
            prov_log_record(open_op);
            prov_log_record(close_op);
        }
    });
}
fn freopen64 = freopen;

/* Need: In case an analysis wants to use open-to-close consistency */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html */
int fclose (FILE *stream) {
    void* pre_call = ({
        int fd = fileno(stream);
        struct Op op = {
            close_op_code,
            {.close = {fd, fd, 0}},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.close.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}
int fcloseall(void) {
    void* pre_call = ({
        struct Op op = {
            close_op_code,
            {.close = {0, INT_MAX, 0}},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.close.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/openat.2.html */
int openat(int dirfd, const char *filename, int flags, ...) {
    size_t varargs_size = sizeof(dirfd) + sizeof(filename) + sizeof(flags) + (has_mode_arg ? sizeof(mode_t) : 0);
    /* Re varag_size, See variadic note on open
     * https://github.com/bminor/glibc/blob/2367bf468ce43801de987dcd54b0f99ba9d62827/sysdeps/unix/sysv/linux/open64.c#L33
     */
    void* pre_call = ({
        bool has_mode_arg = (flags & O_CREAT) != 0 || (flags & __O_TMPFILE) == __O_TMPFILE;
        struct Op op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(dirfd, filename, (flags & O_NOFOLLOW ? AT_SYMLINK_NOFOLLOW : 0)),
                .flags = flags,
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            if (has_mode_arg) {
                va_list ap;
                va_start(ap, flags);
                op.data.open.mode = va_arg(ap, __type_mode_t);
                va_end(ap);
            }
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.open.ferrno = unlikely(ret == -1) ? errno : 0;
            op.data.open.fd = ret;
            prov_log_record(op);
        }
    });
}

fn openat64 = openat;

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html */
int open (const char *filename, int flags, ...) {
    size_t varargs_size = sizeof(filename) + sizeof(flags) + (has_mode_arg ? sizeof(mode_t) : 0);
    /* Re varag_size
     * We use the third-arg (of type mode_t) when ((flags) & O_CREAT) != 0 || ((flags) & __O_TMPFILE) == __O_TMPFILE.
     * https://github.com/bminor/glibc/blob/2367bf468ce43801de987dcd54b0f99ba9d62827/sysdeps/unix/sysv/linux/openat.c#L33
     * https://github.com/bminor/glibc/blob/2367bf468ce43801de987dcd54b0f99ba9d62827/sysdeps/unix/sysv/linux/open.c#L35
     * https://github.com/bminor/glibc/blob/2367bf468ce43801de987dcd54b0f99ba9d62827/io/fcntl.h#L40
     */
    void* pre_call = ({
        bool has_mode_arg = (flags & O_CREAT) != 0 || (flags & __O_TMPFILE) == __O_TMPFILE;
        struct Op op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(AT_FDCWD, filename, (flags & O_NOFOLLOW ? AT_SYMLINK_NOFOLLOW : 0)),
                .flags = flags,
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            if (has_mode_arg) {
                va_list ap;
                va_start(ap, flags);
                op.data.open.mode = va_arg(ap, __type_mode_t);
                va_end(ap);
            }
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.open.ferrno = unlikely(ret == -1) ? errno : 0;
            op.data.open.fd = ret;
            prov_log_record(op);
        }
    });
}
fn open64 = open;
int creat (const char *filename, mode_t mode) {
    void* pre_call = ({
        /**
         * According to docs
         * creat(foo, mode) == open(foo, O_WRONLY|O_CREAT|O_TRUNC, mode)
         * Docs: https://man7.org/linux/man-pages/man3/creat.3p.html */
        struct Op op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = O_WRONLY | O_CREAT | O_TRUNC,
                .mode = mode,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.open.ferrno = unlikely(ret == -1) ? errno : 0;
            op.data.open.fd = ret;
            prov_log_record(op);
        }
    });
}
fn create64 = creat;
int close (int filedes) {
    void* pre_call = ({
        struct Op op = {
            close_op_code,
            {.close = {filedes, filedes, 0}},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
         if (likely(prov_log_is_enabled())) {
            op.data.close.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}
int close_range (unsigned int lowfd, unsigned int maxfd, int flags) {
    void* pre_call = ({
        if (flags != 0) {
            NOT_IMPLEMENTED("I don't know how to handle close_rnage flags yet");
        }
        struct Op op = {
            close_op_code,
            {.close = {lowfd, maxfd, 0}},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
         if (likely(prov_log_is_enabled())) {
            op.data.close.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}
void closefrom (int lowfd) {
    void* pre_call = ({
        struct Op op = {
            close_op_code,
            {.close = {lowfd, INT_MAX, 0}},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
         if (likely(prov_log_is_enabled())) {
            prov_log_record(op);
        }
    });
}

/* TODO: dup family */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Duplicating-Descriptors.html */
int dup (int old) { }
int dup2 (int old, int new) { }

/* Docs: https://www.man7.org/linux/man-pages/man2/dup.2.html */
int dup3 (int old, int new, int flags) { }

/* TODO: fcntl */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Control-Operations.html#index-fcntl-function */
int fcntl (int filedes, int command, ...) {
    void* pre_call = ({
            bool int_arg = command == F_DUPFD || command == F_DUPFD_CLOEXEC || command == F_SETFD || command == F_SETFL || command == F_SETOWN || command == F_SETSIG || command == F_SETLEASE || command == F_NOTIFY || command == F_SETPIPE_SZ || command == F_ADD_SEALS;
            bool ptr_arg = command == F_SETLK || command == F_SETLKW || command == F_GETLK || /* command == F_OLD_SETLK || command == F_OLD_SETLKW || command == F_OLD_GETLK || */ command == F_GETOWN_EX || command == F_SETOWN_EX || command == F_GET_RW_HINT || command == F_SET_RW_HINT || command == F_GET_FILE_RW_HINT || command == F_SET_FILE_RW_HINT;
            /* Highlander assertion: there can only be one! */
            /* But there could be zero, as in fcntl(fd, F_GETFL) */
            assert(!int_arg || !ptr_arg);
        });
    size_t varargs_size = sizeof(filedes) + sizeof(command) + (
        int_arg ? sizeof(int)
        : ptr_arg ? sizeof(void*)
        : 0
    );
    /* Variadic:
     * https://www.man7.org/linux/man-pages/man2/fcntl.2.html
     * "The required argument type is indicated in parentheses after each cmd name" */
}

/* Need: We need this so that opens relative to the current working directory can be resolved */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Working-Directory.html */
int chdir (const char *filename) {
    void* pre_call = ({
        struct Op op = {
            chdir_op_code,
            {.chdir = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .ferrno = 0
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.chdir.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}
int fchdir (int filedes) {
    void* pre_call = ({
        struct Op op = {
            chdir_op_code,
            {.chdir = {
                .path = create_path_lazy(filedes, "", AT_EMPTY_PATH),
                .ferrno = 0
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.chdir.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-a-Directory.html */
DIR * opendir (const char *dirname) {
    void* pre_call = ({
        struct Op op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(AT_FDCWD, dirname, 0),
                /* https://github.com/esmil/musl/blob/master/src/dirent/opendir.c */
                .flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.open.ferrno = ret == NULL ? errno : 0;
            op.data.open.fd = try_dirfd(ret);
            prov_log_record(op);
        }
    });
}
DIR * fdopendir (int fd) {
    void* pre_call = ({
        struct Op op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(fd, "", AT_EMPTY_PATH),
                /* https://github.com/esmil/musl/blob/master/src/dirent/opendir.c */
                .flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.open.ferrno = ret == NULL ? errno : 0;
            op.data.open.fd = try_dirfd(ret);
            prov_log_record(op);
        }
    });
}

/* TODO: dirent manipulation */
/* https://www.gnu.org/software/libc/manual/html_node/Reading_002fClosing-Directory.html */
struct dirent * readdir (DIR *dirstream) {
    void* pre_call = ({
        int fd = try_dirfd(dirstream);
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, "", AT_EMPTY_PATH),
                .child = NULL,
                .all_children = false,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == NULL) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                /* Note: we will assume these dirents aer the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(get_data_arena(), ret->d_name, sizeof(ret->d_name));
            }
            prov_log_record(op);
        }
    });
}
int readdir_r (DIR *dirstream, struct dirent *entry, struct dirent **result) {
    void* pre_call = ({
        int fd = try_dirfd(dirstream);
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, "", AT_EMPTY_PATH),
                .child = NULL,
                .all_children = false,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (*result == NULL) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                /* Note: we will assume these dirents aer the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(get_data_arena(), entry->d_name, sizeof(entry->d_name));
            }
            prov_log_record(op);
        }
    });
}
struct dirent64 * readdir64 (DIR *dirstream) {
    void* pre_call = ({
        int fd = try_dirfd(dirstream);
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, "", AT_EMPTY_PATH),
                .child = NULL,
                .all_children = false,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == NULL) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                /* Note: we will assume these dirents aer the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(get_data_arena(), ret->d_name, sizeof(ret->d_name));
            }
            prov_log_record(op);
        }
    });
}
int readdir64_r (DIR *dirstream, struct dirent64 *entry, struct dirent64 **result) {
    void* pre_call = ({
        int fd = try_dirfd(dirstream);
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, "", AT_EMPTY_PATH),
                .child = NULL,
                .all_children = false,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (*result == NULL) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                /* Note: we will assume these dirents aer the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(get_data_arena(), entry->d_name, sizeof(entry->d_name));
            }
            prov_log_record(op);
        }
    });
}
int closedir (DIR *dirstream) {
    void* pre_call = ({
        int fd = try_dirfd(dirstream);
        struct Op op = {
            close_op_code,
            {.close = {fd, fd, 0}},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.close.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}

/* https://www.gnu.org/software/libc/manual/html_node/Random-Access-Directory.html */
void rewinddir (DIR *dirstream) { }
long int telldir (DIR *dirstream) { }
void seekdir (DIR *dirstream, long int pos) { }

/* https://www.gnu.org/software/libc/manual/html_node/Scanning-Directory-Content.html */
int scandir (const char *dir, struct dirent ***namelist, int (*selector) (const struct dirent *), int (*cmp) (const struct dirent **, const struct dirent **)) {
    void* pre_call = ({
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(AT_FDCWD, dir, 0),
                .child = NULL,
                .all_children = true,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int scandir64 (const char *dir, struct dirent64 ***namelist, int (*selector) (const struct dirent64 *), int (*cmp) (const struct dirent64 **, const struct dirent64 **)) {
    void* pre_call = ({
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(AT_FDCWD, dir, 0),
                .child = NULL,
                .all_children = true,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man3/scandir.3.html */
int scandirat(int dirfd, const char *restrict dirp,
            struct dirent ***restrict namelist,
            int (*filter)(const struct dirent *),
            int (*compar)(const struct dirent **, const struct dirent **)) {
    void* pre_call = ({
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(dirfd, dirp, 0),
                .child = NULL,
                .all_children = true,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}

/* https://www.gnu.org/software/libc/manual/html_node/Low_002dlevel-Directory-Access.html */
ssize_t getdents64 (int fd, void *buffer, size_t length) {
    void* pre_call = ({
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, "", AT_EMPTY_PATH),
                .child = NULL,
                .all_children = true,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Working-with-Directory-Trees.html */
/* Need: These operations walk a directory recursively */
int ftw (const char *filename, __ftw_func_t func, int descriptors) {
    void* pre_call = ({
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(AT_FDCWD, filename, 0),
                .child = NULL,
                .all_children = true,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int ftw64 (const char *filename, __ftw64_func_t func, int descriptors) {
    void* pre_call = ({
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(AT_FDCWD, filename, 0),
                .child = NULL,
                .all_children = true,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int nftw (const char *filename, __nftw_func_t func, int descriptors, int flag) {
    void* pre_call = ({
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(AT_FDCWD, filename, 0),
                .child = NULL,
                .all_children = true,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int nftw64 (const char *filename, __nftw64_func_t func, int descriptors, int flag) {
    void* pre_call = ({
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(AT_FDCWD, filename, 0),
                .child = NULL,
                .all_children = true,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
/* I can't include ftw.h on some systems because it defines fstatat as extern int on Sandia machines. */

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Hard-Links.html */
int link (const char *oldname, const char *newname) { }
int linkat (int oldfd, const char *oldname, int newfd, const char *newname, int flags) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html */
int symlink (const char *oldname, const char *newname) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html */
int symlinkat(const char *target, int newdirfd, const char *linkpath) { }
ssize_t readlink (const char *filename, char *buffer, size_t size) { }
ssize_t readlinkat (int dirfd, const char *filename, char *buffer, size_t size) { }
char * canonicalize_file_name (const char *name) { }
char * realpath (const char *restrict name, char *restrict resolved) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Deleting-Files.html */
int unlink (const char *filename) { }
int rmdir (const char *filename) { }
int remove (const char *filename) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Renaming-Files.html */
int rename (const char *oldname, const char *newname) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Creating-Directories.html */
int mkdir (const char *filename, mode_t mode) { }

/* Docs: https://www.man7.org/linux/man-pages/man2/mkdirat.2.html  */
int mkdirat(int dirfd, const char *pathname, mode_t mode) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Reading-Attributes.html */
int stat (const char *filename, struct stat *buf) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = 0,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                stat_to_statx(&op.data.stat.statx_buf, buf);
            }
            prov_log_record(op);
        }
    });
}
int stat64 (const char *filename, struct stat64 *buf) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = 0,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                stat64_to_statx(&op.data.stat.statx_buf, buf);
            }
            prov_log_record(op);
        }
    });
}
int fstat (int filedes, struct stat *buf) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(filedes, "", AT_EMPTY_PATH),
                .flags = 0,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                stat_to_statx(&op.data.stat.statx_buf, buf);
            }
            prov_log_record(op);
        }
    });
}
int fstat64 (int filedes, struct stat64 * restrict buf) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(filedes, "", AT_EMPTY_PATH),
                .flags = 0,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                stat64_to_statx(&op.data.stat.statx_buf, buf);
            }
            prov_log_record(op);
        }
    });
}
int lstat (const char *filename, struct stat *buf) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(AT_FDCWD, filename, AT_SYMLINK_NOFOLLOW),
                .flags = AT_SYMLINK_NOFOLLOW,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                stat_to_statx(&op.data.stat.statx_buf, buf);
            }
            prov_log_record(op);
        }
    });
}
int lstat64 (const char *filename, struct stat64 *buf) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(AT_FDCWD, filename, AT_SYMLINK_NOFOLLOW),
                .flags = AT_SYMLINK_NOFOLLOW,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                stat64_to_statx(&op.data.stat.statx_buf, buf);
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/statx.2.html */
int statx(int dirfd, const char *restrict pathname, int flags, unsigned int mask, struct statx *restrict statxbuf) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(dirfd, pathname, flags),
                .flags = flags,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                op.data.stat.statx_buf = *statxbuf;
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://linux.die.net/man/2/fstatat */
int fstatat(int dirfd, const char * restrict pathname, struct stat * restrict buf, int flags) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(dirfd, pathname, flags),
                .flags = flags,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                stat_to_statx(&op.data.stat.statx_buf, buf);
            }
            prov_log_record(op);
        }
    });
}

int fstatat64 (int fd, const char * restrict file, struct stat64 * restrict buf, int flags) {
    void* pre_call = ({
        struct Op op = {
            stat_op_code,
            {.stat = {
                .path = create_path_lazy(fd, file, flags),
                .flags = flags,
                .statx_buf = {0},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            } else {
                stat64_to_statx(&op.data.stat.statx_buf, buf);
            }
            prov_log_record(op);
        }
    });
}
/* fn newfstatat = fstatat; */

/* Docs: https://www.gnu.org/software/libc/manual/html_node/File-Owner.html */
int chown (const char *filename, uid_t owner, gid_t group) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = 0,
                .kind = MetadataOwnership,
                .value = {
                    .ownership = {
                        .uid = owner,
                        .gid = group,
                    },
                },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int fchown (int filedes, uid_t owner, gid_t group) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(filedes, "", AT_EMPTY_PATH),
                .flags = AT_EMPTY_PATH,
                .kind = MetadataOwnership,
                .value = {
                    .ownership = {
                        .uid = owner,
                        .gid = group,
                    },
                },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}

// https://www.man7.org/linux/man-pages/man2/lchown.2.html
int lchown(const char *pathname, uid_t owner, gid_t group) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(AT_FDCWD, pathname, AT_SYMLINK_NOFOLLOW),
                .flags = AT_SYMLINK_NOFOLLOW,
                .kind = MetadataOwnership,
                .value = {
                    .ownership = {
                        .uid = owner,
                        .gid = group,
                    },
                },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int fchownat(int dirfd, const char *pathname, uid_t owner, gid_t group, int flags) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(dirfd, pathname, flags),
                .flags = flags,
                .kind = MetadataOwnership,
                .value = {
                    .ownership = {
                        .uid = owner,
                        .gid = group,
                    },
                },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}


/* Docs: https://www.gnu.org/software/libc/manual/html_node/Setting-Permissions.html  */
int chmod (const char *filename, mode_t mode) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = 0,
                .kind = MetadataMode,
                .value = {
                    .mode = mode,
                },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int fchmod (int filedes, mode_t mode) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(filedes, "", AT_EMPTY_PATH),
                .flags = AT_EMPTY_PATH,
                .kind = MetadataMode,
                .value = {
                    .mode = mode,
                },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/chmod.2.html */
int fchmodat(int dirfd, const char *pathname, mode_t mode, int flags) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(dirfd, pathname, flags),
                .flags = flags,
                .kind = MetadataMode,
                .value = {
                    .mode = mode,
                },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Testing-File-Access.html */
int access (const char *filename, int how) {
    void* pre_call = ({
        struct Op op = {
            access_op_code,
            {.access = {
                create_path_lazy(AT_FDCWD, filename, 0), how, 0, 0}
            },
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.access.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man3/faccessat.3p.html */
int faccessat(int dirfd, const char *pathname, int mode, int flags) {
    void* pre_call = ({
        struct Op op = {
            access_op_code,
            {.access = {
                .path = create_path_lazy(dirfd, pathname, 0 /* Wrong kind of flags */),
                .mode = mode,
                .flags = flags,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.access.ferrno = ret == 0 ? 0 : errno;
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/File-Times.html */
int utime (const char *filename, const struct utimbuf *times) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = 0,
                .kind = MetadataTimes,
                .value = { 0 },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (times) {
            op.data.update_metadata.value.times.is_null = false;
            op.data.update_metadata.value.times.atime.tv_sec = times->actime;
            op.data.update_metadata.value.times.mtime.tv_sec = times->modtime;
        } else {
            op.data.update_metadata.value.times.is_null = true;
        }
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int utimes (const char *filename, const struct timeval tvp[2]) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(AT_FDCWD, filename, 0),
                .flags = 0,
                .kind = MetadataTimes,
                .value = { 0 },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (tvp) {
            op.data.update_metadata.value.times.is_null = false;
            op.data.update_metadata.value.times.atime = tvp[0];
            op.data.update_metadata.value.times.mtime = tvp[1];
        } else {
            op.data.update_metadata.value.times.is_null = true;
        }
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int lutimes (const char *filename, const struct timeval tvp[2]) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(AT_FDCWD, filename, AT_SYMLINK_NOFOLLOW),
                .flags = AT_SYMLINK_NOFOLLOW,
                .kind = MetadataTimes,
                .value = { 0 },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (tvp) {
            op.data.update_metadata.value.times.is_null = false;
            op.data.update_metadata.value.times.atime = tvp[0];
            op.data.update_metadata.value.times.mtime = tvp[1];
        } else {
            op.data.update_metadata.value.times.is_null = true;
        }
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}
int futimes (int fd, const struct timeval tvp[2]) {
    void* pre_call = ({
        struct Op op = {
            update_metadata_op_code,
            {.update_metadata = {
                .path = create_path_lazy(fd, "", AT_EMPTY_PATH),
                .flags = AT_EMPTY_PATH,
                .kind = MetadataTimes,
                .value = { 0 },
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (tvp) {
            op.data.update_metadata.value.times.is_null = false;
            op.data.update_metadata.value.times.atime = tvp[0];
            op.data.update_metadata.value.times.mtime = tvp[1];
        } else {
            op.data.update_metadata.value.times.is_null = true;
        }
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = saved_errno;
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/File-Size.html */
int truncate (const char *filename, off_t length) { }
int truncate64 (const char *name, off64_t length) { }
int ftruncate (int fd, off_t length) { }
int ftruncate64 (int id, off64_t length) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Making-Special-Files.html */
int mknod (const char *filename, mode_t mode, dev_t dev) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Temporary-Files.html */
FILE * tmpfile (void) { }
FILE * tmpfile64 (void) { }
char * tmpnam (char *result) { }
char * tmpnam_r (char *result) { }
char * tempnam (const char *dir, const char *prefix) { }
char * mktemp (char *template) { }
int mkstemp (char *template) { }
char * mkdtemp (char *template) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Executing-a-File.html */
/* Need: We need this because exec kills all global variables, we need to dump our tables before continuing */
int execv (const char *filename, char *const argv[]) {
    void* pre_call = ({
        putenv_probe_vars();
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(0, filename, 0),
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        /*
         * If exec is successful {
         *   Exec should jump to a new process.
         *   It won't return here.
         *   If the process has _any_ side-effects {
         *     construct_libprov should get called when the first side-effects occur.
         *   } else {
         *     A tree fell in the forest and nobody was around to hear it. It didn't make a sound.
         *     A process launched in the system and it never made any side-effects. We don't care about it for the sake of provenance.
         *   }
         * } else {
         *   Exec returns here.
         *   There must have been an error
         * }
         * */
        if (likely(prov_log_is_enabled())) {
            assert(errno > 0);
            op.data.exec.ferrno = saved_errno;
            prov_log_record(op);
        }
    });
}
int execl (const char *filename, const char *arg0, ...) {
    void* pre_call = ({
        putenv_probe_vars();
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(0, filename, 0),
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            assert(errno > 0);
            op.data.exec.ferrno = saved_errno;
            prov_log_record(op);
        }
    });
    size_t varargs_size = sizeof(char*) + (COUNT_NONNULL_VARARGS(arg0) + 1) * sizeof(char*);
}
int execve (const char *filename, char *const argv[], char *const env[]) {
    void* pre_call = ({
        env = update_env_with_probe_vars(env);
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(0, filename, 0),
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
        DEBUG("in Execve");
    });
    void* post_call = ({
        free((char**) env); // This is our own malloc from update_env_with_probe_vars, so it should be safe to free
        if (likely(prov_log_is_enabled())) {
            assert(errno > 0);
            op.data.exec.ferrno = saved_errno;
            prov_log_record(op);
        }
    });
}
int fexecve (int fd, char *const argv[], char *const env[]) {
    void* pre_call = ({
        env = update_env_with_probe_vars(env);
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(fd, "", AT_EMPTY_PATH),
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        free((char**) env); // This is our own malloc from update_env_with_probe_vars, so it should be safe to free
        if (likely(prov_log_is_enabled())) {
            assert(errno > 0);
            op.data.exec.ferrno = saved_errno;
            prov_log_record(op);
        }
    });
}
int execle (const char *filename, const char *arg0, ...) {
    void* pre_call = ({
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(0, filename, 0),
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
        ERROR("Not implemented; I need to figure out how to update the environment.");
    });
    void* call = ({
        size_t argc = COUNT_NONNULL_VARARGS(arg0);
        char** arg_vec = malloc(argc * sizeof(char*));
        va_list ap;
		va_start(ap, arg0);
        for (size_t i = 0; i < argc - 1; ++i) {
            arg_vec[i] = va_arg(ap, __type_charp);
        }
        char** env = va_arg(ap, __type_charpp);
        va_end(ap);
        char * const* updated_env = update_env_with_probe_vars(env);
        int ret = unwrapped_execve(filename, arg_vec, updated_env);
    });
    void* post_call = ({
        free((char**)updated_env);
        if (likely(prov_log_is_enabled())) {
            assert(errno > 0);
            op.data.exec.ferrno = saved_errno;
            prov_log_record(op);
        }
    });
    size_t varargs_size = sizeof(char*) + (COUNT_NONNULL_VARARGS(arg0) + 1) * sizeof(char*);
}
int execvp (const char *filename, char *const argv[]) {
    void* pre_call = ({
        putenv_probe_vars();
        char* bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
        bool found = lookup_on_path(filename, bin_path);
        struct Op op = {
            exec_op_code,
            {.exec = {
                /* maybe we could get rid of this allocation somehow
                 * i.e., construct the .path in-place
                 * */
                .path = found ? create_path_lazy(0, bin_path, 0) : null_path,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            assert(errno > 0);
            op.data.exec.ferrno = saved_errno;
            prov_log_record(op);
        }
    });
}
int execlp (const char *filename, const char *arg0, ...) {
    size_t varargs_size = sizeof(char*) + (COUNT_NONNULL_VARARGS(arg0) + 1) * sizeof(char*);
    void* pre_call = ({
        putenv_probe_vars();
        char* bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
        bool found = lookup_on_path(filename, bin_path);
        struct Op op = {
            exec_op_code,
            {.exec = {
                /* maybe we could get rid of this allocation somehow
                 * i.e., construct the .path in-place
                 * */
                .path = found ? create_path_lazy(0, bin_path, 0) : null_path,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            assert(errno > 0);
            op.data.exec.ferrno = saved_errno;
            prov_log_record(op);
        }
    });
}

/* Docs: https://linux.die.net/man/3/execvpe1 */
int execvpe(const char *filename, char *const argv[], char *const envp[]) {
    void* pre_call = ({
        envp = update_env_with_probe_vars(envp);
        char* bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
        bool found = lookup_on_path(filename, bin_path);
        struct Op op = {
            exec_op_code,
            {.exec = {
                /* maybe we could get rid of this allocation somehow
                 * i.e., construct the .path in-place
                 * */
                .path = found ? create_path_lazy(0, bin_path, 0) : null_path,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        free((char**) envp); // This is our own malloc from update_env_with_probe_vars, so it should be safe to free
        if (likely(prov_log_is_enabled())) {
            assert(errno > 0);
            op.data.exec.ferrno = saved_errno;
            prov_log_record(op);
        }
    });
}

/* Need: Fork does copy-on-write, so we want to deduplicate our structures first */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Creating-a-Process.html */
pid_t fork (void) {
    void* pre_call = ({
        struct Op op = {
            clone_op_code,
            {.clone = {
                /* As far as I can tell, fork has the same semantics as calling clone with flags == 0.
                 * I could be wrong.
                 * */
                .flags = 0,
                .run_pthread_atfork_handlers = true,
                .task_type = TASK_PID,
                .task_id = -1,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                /* Failure */
                op.data.clone.ferrno = saved_errno;
                prov_log_record(op);
            } else if (ret == 0) {
                reinit_process();
            } else {
                /* Success; parent */
                op.data.clone.task_id = ret;
                prov_log_record(op);
            }
        }
    });
}
pid_t _Fork (void) {
     void* pre_call = ({
        struct Op op = {
            clone_op_code,
            {.clone = {
                /* As far as I can tell, fork has the same semantics as calling clone with flags == 0.
                 * I could be wrong.
                 * */
                .flags = 0,
                .run_pthread_atfork_handlers = false,
                .task_type = TASK_PID,
                .task_id = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                /* Failure */
                op.data.clone.ferrno = saved_errno;
                prov_log_record(op);
            } else if (ret == 0) {
                /* Success; child */
                reinit_process();
            } else {
                /* Success; parent */
                op.data.clone.task_id = ret;
                prov_log_record(op);
            }
        }
    });
}
pid_t vfork (void) {
    /* NOTE: I think vfork, as defined, is un-interposable.
     * THe Linux manual clearly states:
     *
     * > the behavior is undefined if the process created by vfork()...
     * > returns from the function in which vfork() was called...
     * > before successfully calling _exit(2) or one of the exec(3) family of functions.
     *
     * Suppose client code reads:
     *
     *     if (vfork()) {
     *         exec(...)
     *     }
     *
     * With interposition, we would encounter the following stack states:
     *
     *     client_code
     *     client_code > wrapped_vfork
     *     client_code > wrapped_vfork > real_vfork
     *     client_code > wrapped_vfork
     *     client_code
     *     client_code > wrapped_exec
     *     client_code > wrapped_exec > real_vfork
     *     client_code > wrapped_exec
     *
     * Without interposition, client_code calls real_vfork then real_exec.
     * But with interposition, client_code calls wrapped_vfork calls real_vfork.
     * Then wrapped_vfork must return before client code calls wrapped_exec which calls real_exec.
     * However, returning from wrapped_vfork, as I understand the Linux documentation, induces undefined behavior.
     *
     * Therefore, I will interpose vfork by translating it into a regular fork, which bears no such limitation.
     * No program will notice, since the functional guarantees of vfork are a strict subset of the functional guarantees of fork (vfork without the limitations).
     * There may be a slight performance degradation, but it should be slight.
     * */
    void* pre_call = ({
        struct Op op = {
            clone_op_code,
            {.clone = {
                .flags = 0,
                .run_pthread_atfork_handlers = true,
                .task_type = TASK_PID,
                .task_id = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
        } else {
            prov_log_save();
        }
    });
    void* call = ({
        int ret = unwrapped_fork();
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                /* Failure */
                op.data.clone.ferrno = saved_errno;
                prov_log_record(op);
            } else if (ret == 0) {
                reinit_process();
            } else {
                /* Success; parent */
                op.data.clone.task_id = ret;
                prov_log_record(op);
            }
        }
    });
}

/* Docs: https://man7.org/linux/man-pages/man2/clone.2.html */
int clone(
	  fn_ptr_int_void_ptr fn,
	  void *stack,
	  int flags,
      void * arg,
	  ...
	  /* pid_t *_Nullable parent_tid, */
	  /* void *_Nullable tls, */
	  /* pid_t *_Nullable child_tid */
) {
    size_t varargs_size = sizeof(void*) + sizeof(void*) + sizeof(int) + (COUNT_NONNULL_VARARGS(arg) + 1) * sizeof(void*) + sizeof(pid_t*) + sizeof(void*) + sizeof(pid_t*);
    void* pre_call = ({
        (void) fn;
        (void) stack;
        (void) arg;
        // Disable vfork()
        // See vfork() for reasons.
        flags = flags &~CLONE_VFORK;
        struct Op op = {
            clone_op_code,
            {.clone = {
                /* As far as I can tell, fork has the same semantics as calling clone with flags == 0.
                 * I could be wrong.
                 * */
                .flags = flags,
                .run_pthread_atfork_handlers = false,
                .task_type = (flags & CLONE_THREAD) ? TASK_TID : TASK_PID,
                .task_id = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
            if ((flags & CLONE_THREAD) != (flags & CLONE_VM)) {
                NOT_IMPLEMENTED("I conflate cloning a new thread (resulting in a process with the same PID, new TID) with sharing the memory space. If CLONE_SIGHAND is set, then Linux asserts CLONE_THREAD == CLONE_VM; If it is not set and CLONE_THREAD != CLONE_VM, by a real application, I will consider disentangling the assumptions (required to support this combination).");
            }
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        if (unlikely(ret == -1)) {
            /* Failure */
            if (likely(prov_log_is_enabled())) {
                op.data.clone.ferrno = saved_errno;
                prov_log_record(op);
            }
        } else if (ret == 0) {
            /* Success; child. */
            if (flags & CLONE_THREAD) {
                maybe_init_thread();
            } else {
                reinit_process();
            }
        } else {
            /* Success; parent */
            if (likely(prov_log_is_enabled())) {
                op.data.clone.task_id = ret;
                prov_log_record(op);
            }
        }
   });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Process-Completion.html */
pid_t waitpid (pid_t pid, int *status_ptr, int options) {
    void* pre_call = ({
        int status;
        if (status_ptr == NULL) {
            status_ptr = &status;
        }
        struct Op op = {
            wait_op_code,
            {.wait = {
                .task_type = TASK_PID,
                .task_id = 0,
                .options = options,
                .status = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        prov_log_try(op);
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                op.data.wait.ferrno = saved_errno;
            } else {
                op.data.wait.task_id = ret;
                op.data.wait.status = *status_ptr;
            }
            prov_log_record(op);
        }
   });
}
pid_t wait (int *status_ptr) {
    void* pre_call = ({
        int status;
        if (status_ptr == NULL) {
            status_ptr = &status;
        }
        struct Op op = {
            wait_op_code,
            {.wait = {
                .task_type = TASK_PID,
                .task_id = -1,
                .options = 0,
                .status = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        prov_log_try(op);
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                op.data.wait.ferrno = saved_errno;
            } else {
                op.data.wait.task_id = ret;
                op.data.wait.status = *status_ptr;
            }
            prov_log_record(op);
        }
   });
}
pid_t wait4 (pid_t pid, int *status_ptr, int options, struct rusage *usage) {
    void* pre_call = ({
        struct Op wait_op = {
            wait_op_code,
            {.wait = {
                .task_type = TASK_TID,
                .task_id = 0,
                .options = options,
                .status = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        prov_log_try(wait_op);
        struct Op getrusage_op = {
            getrusage_op_code,
            {.getrusage = {
                .waitpid_arg = pid,
                .getrusage_arg = 0,
                .usage = {{0}},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (usage) {
            prov_log_try(getrusage_op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                wait_op.data.wait.ferrno = saved_errno;
                if (usage) {
                    getrusage_op.data.getrusage.ferrno = saved_errno;
                }
            } else {
                wait_op.data.wait.task_id = ret;
                wait_op.data.wait.status = *status_ptr;
                if (usage) {
                    memcpy(&getrusage_op.data.getrusage.usage, usage, sizeof(struct rusage));
                }
            }
            prov_log_record(wait_op);
            if (usage) {
                prov_log_record(getrusage_op);
            }
        }
   });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/BSD-Wait-Functions.html */
pid_t wait3 (int *status_ptr, int options, struct rusage *usage) {
    void* pre_call = ({
        struct Op wait_op = {
            wait_op_code,
            {.wait = {
                .task_type = TASK_PID,
                .task_id = 0,
                .options = options,
                .status = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        prov_log_try(wait_op);
        struct Op getrusage_op = {
            getrusage_op_code,
            {.getrusage = {
                .waitpid_arg = -1,
                .getrusage_arg = 0,
                .usage = {{0}},
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        if (usage) {
            prov_log_try(getrusage_op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                wait_op.data.wait.ferrno = saved_errno;
                if (usage) {
                    getrusage_op.data.getrusage.ferrno = saved_errno;
                }
            } else {
                wait_op.data.wait.task_id = ret;
                wait_op.data.wait.status = *status_ptr;
                if (usage) {
                    memcpy(&getrusage_op.data.getrusage.usage, usage, sizeof(struct rusage));
                }
            }
            prov_log_record(wait_op);
            if (usage) {
                prov_log_record(getrusage_op);
            }
        }
   });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/wait.2.html */
int waitid(idtype_t idtype, id_t id, siginfo_t *infop, int options) {
    void* pre_call = ({
        struct Op wait_op = {
            wait_op_code,
            {.wait = {
                .task_type = TASK_TID,
                .task_id = 0,
                .options = options,
                .status = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
        prov_log_try(wait_op);
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (unlikely(ret == -1)) {
                wait_op.data.wait.ferrno = saved_errno;
            } else {
                wait_op.data.wait.task_id = infop->si_pid;
                wait_op.data.wait.status = infop->si_status;
            }
            prov_log_record(wait_op);
        }
   });
}

/* https://www.gnu.org/software/libc/manual/html_node/ISO-C-Thread-Management.html */
int thrd_create (thrd_t *thr, thrd_start_t func, void *arg) {
    void* pre_call = ({
        struct Op op = {
            clone_op_code,
            {.clone = {
                .flags = CLONE_FILES | CLONE_FS | CLONE_IO | CLONE_PARENT | CLONE_SIGHAND | CLONE_THREAD | CLONE_VM,
                .task_type = TASK_ISO_C_THREAD,
                .task_id = 0,
                .run_pthread_atfork_handlers = false,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
    });
    void* post_call = ({
        if (unlikely(ret != thrd_success)) {
            /* Failure */
            if (likely(prov_log_is_enabled())) {
                op.data.clone.ferrno = saved_errno;
                prov_log_record(op);
            }
        } else {
            /* Success; parent */
            if (likely(prov_log_is_enabled())) {
                op.data.clone.task_id = ret;
                prov_log_record(op);
            }
        }
   });
}

int thrd_join (thrd_t thr, int *res) {
    void* pre_call = ({
        struct Op op = {
            wait_op_code,
            {.wait = {
                .task_type = TASK_ISO_C_THREAD,
                .task_id = thr,
                .options = 0,
                .status = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
    });
    void* post_call = ({
        if (unlikely(ret != thrd_success)) {
            /* Failure */
            if (likely(prov_log_is_enabled())) {
                op.data.clone.ferrno = saved_errno;
                prov_log_record(op);
            }
        } else {
            /* Success; parent */
            op.data.wait.status = *res;
            if (likely(prov_log_is_enabled())) {
                prov_log_record(op);
            }
        }
   });
}

/* Docs: https://www.man7.org/linux/man-pages/man3/pthread_create.3.html */
int pthread_create(pthread_t *restrict thread,
                 const pthread_attr_t *restrict attr,
                 void *(*start_routine)(void *),
                 void *restrict arg) {
    void* pre_call = ({
        struct Op op = {
            clone_op_code,
            {.clone = {
                .flags = CLONE_FILES | CLONE_FS | CLONE_IO | CLONE_PARENT | CLONE_SIGHAND | CLONE_THREAD | CLONE_VM,
                .task_type = TASK_PTHREAD,
                .task_id = 0,
                .run_pthread_atfork_handlers = false,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
    });
    void* post_call = ({
        if (unlikely(ret != 0)) {
            /* Failure */
            if (likely(prov_log_is_enabled())) {
                op.data.clone.ferrno = saved_errno;
                prov_log_record(op);
            }
        } else {
            /* Success; parent */
            if (likely(prov_log_is_enabled())) {
                op.data.clone.task_id = *thread;
                prov_log_record(op);
            }
        }
   });
}

int pthread_join(pthread_t thread, void **retval) {
    void* pre_call = ({
        struct Op op = {
            wait_op_code,
            {.wait = {
                .task_type = TASK_PTHREAD,
                .task_id = thread,
                .options = 0,
                .status = 0,
                .ferrno = 0,
            }},
            {0},
            0,
            0,
        };
    });
    void* post_call = ({
        if (unlikely(ret != 0)) {
            /* Failure */
            if (likely(prov_log_is_enabled())) {
                op.data.clone.ferrno = saved_errno;
                prov_log_record(op);
            }
        } else {
            /* Success; parent */
            if (likely(prov_log_is_enabled())) {
                prov_log_record(op);
            }
        }
   });
}

/* void exit (int status) { */
/*     void* pre_call = ({ */
/*         struct Op op = { */
/*             exit_op_code, */
/*             {.exit = { */
/*                 .status = status, */
/*                 .run_atexit_handlers = true, */
/*             }}, */
/*         }; */
/*         prov_log_try(op); */
/*         prov_log_record(op); */
/*         term_process(); */
/*     }); */
/*     void* post_call = ({ */
/*         __builtin_unreachable(); */
/*     }); */
/* } */

/* void _exit(int status) { */
/*     void* pre_call = ({ */
/*         struct Op op = { */
/*             exit_op_code, */
/*             {.exit = { */
/*                 .status = status, */
/*                 .run_atexit_handlers = false, */
/*             }}, */
/*         }; */
/*         prov_log_try(op); */
/*         prov_log_record(op); */
/*         term_process(); */
/*     }); */
/*     void* post_call = ({ */
/*         __builtin_unreachable(); */
/*     }); */
/* } */

/* fn _Exit = _exit; */

/*
** TODO: getcwd, getwd, chroot
 */
