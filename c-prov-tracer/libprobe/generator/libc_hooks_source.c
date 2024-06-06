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

typedef int (*fn_ptr_int_void_ptr)(void*);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html */
FILE * fopen (const char *filename, const char *opentype) {
    void* pre_call = ({
        struct Op op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(AT_FDCWD, filename),
                .flags = fopen_to_flags(opentype),
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == NULL) {
                op.data.open.ferrno = errno;
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
                .path = create_path_lazy(AT_FDCWD, filename),
                .flags = fopen_to_flags(opentype),
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
        };
        struct Op close_op = {
            close_op_code,
            {.close = {original_fd, original_fd, 0}},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(open_op);
            prov_log_try(close_op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == NULL) {
                open_op.data.open.ferrno = errno;
                close_op.data.close.ferrno = errno;
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

/* Docs: https://linux.die.net/man/2/openat */
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
                .path = create_path_lazy(dirfd, filename),
                .flags = flags,
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
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
            op.data.open.ferrno = ret == -1 ? errno : 0;
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
                .path = create_path_lazy(AT_FDCWD, filename),
                .flags = flags,
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
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
            op.data.open.ferrno = ret == -1 ? errno : 0;
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
                .path = create_path_lazy(AT_FDCWD, filename),
                .flags = O_WRONLY | O_CREAT | O_TRUNC,
                .mode = mode,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.open.ferrno = ret == -1 ? errno : 0;
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
            {.chdir = {create_path_lazy(AT_FDCWD, filename), 0}},
            {0},
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
            {.chdir = {create_path_lazy(filedes, NULL), 0}},
            {0},
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
                .path = create_path_lazy(AT_FDCWD, dirname),
                /* https://github.com/esmil/musl/blob/master/src/dirent/opendir.c */
                .flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.open.ferrno = ret == NULL ? errno : 0;
            op.data.open.fd = dirfd(ret);
            prov_log_record(op);
        }
    });
}
DIR * fdopendir (int fd) {
    void* pre_call = ({
        struct Op op = {
            open_op_code,
            {.open = {
                .path = create_path_lazy(fd, NULL),
                /* https://github.com/esmil/musl/blob/master/src/dirent/opendir.c */
                .flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
                .mode = 0,
                .fd = -1,
                .ferrno = 0,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            op.data.open.ferrno = ret == NULL ? errno : 0;
            op.data.open.fd = dirfd(ret);
            prov_log_record(op);
        }
    });
}

/* TODO: dirent manipulation */
/* https://www.gnu.org/software/libc/manual/html_node/Reading_002fClosing-Directory.html */
struct dirent * readdir (DIR *dirstream) {
    void* pre_call = ({
        int fd = dirfd(dirstream);
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, NULL),
                .child = NULL,
                .all_children = false,
                .ferrno = 0,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == NULL) {
                op.data.readdir.ferrno = errno;
            } else {
                /* Note: we will assume these dirents aer the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(&data_arena, ret->d_name, PATH_MAX);
            }
            prov_log_record(op);
        }
    });
}
int readdir_r (DIR *dirstream, struct dirent *entry, struct dirent **result) {
    void* pre_call = ({
        int fd = dirfd(dirstream);
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, NULL),
                .child = NULL,
                .all_children = false,
                .ferrno = 0,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (*result == NULL) {
                op.data.readdir.ferrno = errno;
            } else {
                /* Note: we will assume these dirents aer the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(&data_arena, entry->d_name, PATH_MAX);
            }
            prov_log_record(op);
        }
    });
}
struct dirent64 * readdir64 (DIR *dirstream) {
    void* pre_call = ({
        int fd = dirfd(dirstream);
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, NULL),
                .child = NULL,
                .all_children = false,
                .ferrno = 0,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == NULL) {
                op.data.readdir.ferrno = errno;
            } else {
                /* Note: we will assume these dirents aer the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(&data_arena, ret->d_name, PATH_MAX);
            }
            prov_log_record(op);
        }
    });
}
int readdir64_r (DIR *dirstream, struct dirent64 *entry, struct dirent64 **result) {
    void* pre_call = ({
        int fd = dirfd(dirstream);
        struct Op op = {
            readdir_op_code,
            {.readdir = {
                .dir = create_path_lazy(fd, NULL),
                .child = NULL,
                .all_children = false,
                .ferrno = 0,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (*result == NULL) {
                op.data.readdir.ferrno = errno;
            } else {
                /* Note: we will assume these dirents aer the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(&data_arena, entry->d_name, PATH_MAX);
            }
            prov_log_record(op);
        }
    });
}
int closedir (DIR *dirstream) {
    void* pre_call = ({
        int fd = dirfd(dirstream);
        struct Op op = {
            close_op_code,
            {.close = {fd, fd, 0}},
            {0},
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
                .dir = create_path_lazy(AT_FDCWD, dir),
                .child = NULL,
                .all_children = true,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = errno;
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
                .dir = create_path_lazy(AT_FDCWD, dir),
                .child = NULL,
                .all_children = true,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = errno;
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
                .dir = create_path_lazy(dirfd, dirp),
                .child = NULL,
                .all_children = true,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = errno;
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
                .dir = create_path_lazy(fd, NULL),
                .child = NULL,
                .all_children = true,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret == -1) {
                op.data.readdir.ferrno = errno;
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
                .dir = create_path_lazy(AT_FDCWD, filename),
                .child = NULL,
                .all_children = true,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = errno;
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
                .dir = create_path_lazy(AT_FDCWD, filename),
                .child = NULL,
                .all_children = true,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = errno;
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
                .dir = create_path_lazy(AT_FDCWD, filename),
                .child = NULL,
                .all_children = true,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = errno;
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
                .dir = create_path_lazy(AT_FDCWD, filename),
                .child = NULL,
                .all_children = true,
            }},
            {0},
        };
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
        }
    });
    void* post_call = ({
        if (likely(prov_log_is_enabled())) {
            if (ret != 0) {
                op.data.readdir.ferrno = errno;
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
int stat (const char *filename, struct stat *buf) { }
int stat64 (const char *filename, struct stat64 *buf) { }
int fstat (int filedes, struct stat *buf) { }
int fstat64 (int filedes, struct stat64 * restrict buf) { }
int lstat (const char *filename, struct stat *buf) { }
int lstat64 (const char *filename, struct stat64 *buf) { }

/* Docs: https://www.man7.org/linux/man-pages/man2/statx.2.html */
int statx(int dirfd, const char *restrict pathname, int flags, unsigned int mask, struct statx *restrict statxbuf) { }

/* Docs: https://linux.die.net/man/2/fstatat */
int fstatat(int dirfd, const char * restrict pathname, struct stat * restrict buf, int flags) {}

int fstatat64 (int fd, const char * restrict file, struct stat64 * restrict buf, int flags) { }
/* fn newfstatat = fstatat; */

/* Docs: https://www.gnu.org/software/libc/manual/html_node/File-Owner.html */
int chown (const char *filename, uid_t owner, gid_t group) { }
int fchown (int filedes, uid_t owner, gid_t group) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Setting-Permissions.html  */
int chmod (const char *filename, mode_t mode) { }
int fchmod (int filedes, mode_t mode) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Testing-File-Access.html */
int access (const char *filename, int how) {
    void* pre_call = ({
        struct Op op = {
            access_op_code,
            {.access = {create_path_lazy(AT_FDCWD, filename), how, 0, 0}},
            {0},
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
            {.access = {create_path_lazy(dirfd, pathname), mode, flags, 0}},
            {0},
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
int utime (const char *filename, const struct utimbuf *times) { }
int utimes (const char *filename, const struct timeval tvp[2]) { }
int lutimes (const char *filename, const struct timeval tvp[2]) { }
int futimes (int fd, const struct timeval tvp[2]) { }

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
/* Need: We need this because exec kills all global variables, o we need to dump our tables before continuing */
int execv (const char *filename, char *const argv[]) {
    void* pre_call = ({
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(0, filename),
                .ferrno = 0,
            }},
            {0},
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
            op.data.exec.ferrno = errno;
            prov_log_record(op);
        }
    });
}
int execl (const char *filename, const char *arg0, ...) {
    void* pre_call = ({
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(0, filename),
                .ferrno = 0,
            }},
            {0},
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
            op.data.exec.ferrno = errno;
            prov_log_record(op);
        }
    });
    size_t varargs_size = sizeof(char*) + (COUNT_NONNULL_VARARGS(arg0) + 1) * sizeof(char*);
}
int execve (const char *filename, char *const argv[], char *const env[]) {
    void* pre_call = ({
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(0, filename),
                .ferrno = 0,
            }},
            {0},
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
            op.data.exec.ferrno = errno;
            prov_log_record(op);
        }
    });
}
int fexecve (int fd, char *const argv[], char *const env[]) {
        void* pre_call = ({
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(fd, NULL),
                .ferrno = 0,
            }},
            {0},
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
            op.data.exec.ferrno = errno;
            prov_log_record(op);
        }
    });
}
int execle (const char *filename, const char *arg0, ...) {
    void* pre_call = ({
        struct Op op = {
            exec_op_code,
            {.exec = {
                .path = create_path_lazy(0, filename),
                .ferrno = 0,
            }},
            {0},
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
            op.data.exec.ferrno = errno;
            prov_log_record(op);
        }
    });
    size_t varargs_size = sizeof(char*) + (COUNT_NONNULL_VARARGS(arg0) + 1) * sizeof(char*);
}
int execvp (const char *filename, char *const argv[]) {
    void* pre_call = ({
        char* bin_path = arena_calloc(&data_arena, PATH_MAX + 1, sizeof(char));
        bool found = lookup_on_path(filename, bin_path);
        struct Op op = {
            exec_op_code,
            {.exec = {
                /* maybe we could get rid of this allocation somehow
                 * i.e., construct the .path in-place
                 * */
                .path = found ? create_path_lazy(0, bin_path) : null_path,
                .ferrno = 0,
            }},
            {0},
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
            op.data.exec.ferrno = errno;
            prov_log_record(op);
        }
    });
}
int execlp (const char *filename, const char *arg0, ...) {
    size_t varargs_size = sizeof(char*) + (COUNT_NONNULL_VARARGS(arg0) + 1) * sizeof(char*);
    void* pre_call = ({
        char* bin_path = arena_calloc(&data_arena, PATH_MAX + 1, sizeof(char));
        bool found = lookup_on_path(filename, bin_path);
        struct Op op = {
            exec_op_code,
            {.exec = {
                /* maybe we could get rid of this allocation somehow
                 * i.e., construct the .path in-place
                 * */
                .path = found ? create_path_lazy(0, bin_path) : null_path,
                .ferrno = 0,
            }},
            {0},
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
            op.data.exec.ferrno = errno;
            prov_log_record(op);
        }
    });
}

/* Docs: https://linux.die.net/man/3/execvpe1 */
int execvpe(const char *filename, char *const argv[], char *const envp[]) {
    void* pre_call = ({
        char* bin_path = arena_calloc(&data_arena, PATH_MAX + 1, sizeof(char));
        bool found = lookup_on_path(filename, bin_path);
        struct Op op = {
            exec_op_code,
            {.exec = {
                /* maybe we could get rid of this allocation somehow
                 * i.e., construct the .path in-place
                 * */
                .path = found ? create_path_lazy(0, bin_path) : null_path,
                .ferrno = 0,
            }},
            {0},
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
            op.data.exec.ferrno = errno;
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
                .child_process_id = -1,
                .child_thread_id = -1,
                .ferrno = 0,
            }},
            {0},
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
            if (ret == -1) {
                /* Failure */
                op.data.clone.ferrno = errno;
                prov_log_record(op);
            } else if (ret == 0) {
                __process_inited = false;
                __thread_inited = false;
                maybe_init_thread();
            } else {
                /* Success; parent */
                op.data.clone.child_process_id = ret;
                /* Since fork makes processes, child TID = child PID */
                op.data.clone.child_thread_id = ret;
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
                .child_process_id = -1,
                .child_thread_id = -1,
                .ferrno = 0,
            }},
            {0},
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
            if (ret == -1) {
                /* Failure */
                op.data.clone.ferrno = errno;
                prov_log_record(op);
            } else if (ret == 0) {
                /* Success; child */
                __process_inited = false;
                __thread_inited = false;
                maybe_init_thread();
            } else {
                /* Success; parent */
                op.data.clone.child_process_id = ret;
                /* Since fork makes processes, child TID = child PID */
                op.data.clone.child_thread_id = ret;
                prov_log_record(op);
            }
        }
    });
}
pid_t vfork (void) {
    void* pre_call = ({
        struct Op op = {
            clone_op_code,
            {.clone = {
                /* As far as I can tell, fork has the same semantics as calling clone with flags == 0.
                 * I could be wrong.
                 * */
                .flags = CLONE_VFORK,
                .run_pthread_atfork_handlers = false,
                .child_process_id = -1,
                .child_thread_id = -1,
                .ferrno = 0,
            }},
            {0},
        };
        bool was_prov_log_enabled = prov_log_is_enabled();
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
            /* It seems we can't do anything here...
             * > the behavior is undefined if the process created by vfork() either modifies any data other than a variable of type pid_t used to store the return value from vfork(), or returns from the function in which vfork() was called, or calls any other function before successfully calling _exit(2) or one of the exec(3) family of functions.
             * httpss://man7.org/linux/man-pages/man2/vfork.2.html
             * At least the client has to call execve, so we will get a fresh prov buffer when they do that.
             * I really hope returning from this function is fine even though it is technically undefined behavior...
             **/
            prov_log_disable();
            NOT_IMPLEMENTED("vfork");
        } else {
            prov_log_save();
            prov_log_disable();
        }
    });
    void* post_call = ({
        if (ret == -1) {
            /* Failure */
            prov_log_set_enabled(was_prov_log_enabled);
            if (likely(prov_log_is_enabled())) {
                op.data.clone.ferrno = errno;
                prov_log_record(op);
            }
        } else if (ret == 0) {
            /* Success; child. Can't do anything here. */
        } else {
            /* Success; parent */
            prov_log_set_enabled(was_prov_log_enabled);
            if (likely(prov_log_is_enabled())) {
                op.data.clone.child_process_id = ret;
                op.data.clone.child_thread_id = ret; /* Since fork makes processes, child TID = child PID */
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
        /* Mark these variables as used to suppress "unused variable" compiler warning" */
        (void) fn;
        (void) stack;
        struct Op op = {
            clone_op_code,
            {.clone = {
                /* As far as I can tell, fork has the same semantics as calling clone with flags == 0.
                 * I could be wrong.
                 * */
                .flags = flags,
                .run_pthread_atfork_handlers = false,
                .child_process_id = -1,
                .child_thread_id = -1,
                .ferrno = 0,
            }},
            {0},
        };
        bool was_prov_log_enabled = prov_log_is_enabled();
        if (likely(prov_log_is_enabled())) {
            prov_log_try(op);
            prov_log_save();
            if (flags & CLONE_VFORK) {
                prov_log_disable();
                NOT_IMPLEMENTED("vfork");
            }
        } else {
            prov_log_save();
        }
    });
    void* post_call = ({
        if (ret == -1) {
            /* Failure */
            if (flags & CLONE_VFORK) {
                prov_log_set_enabled(was_prov_log_enabled);
            }
            if (likely(prov_log_is_enabled())) {
                op.data.clone.ferrno = errno;
                prov_log_record(op);
            }
        } else if (ret == 0) {
            /* Success; child. */
            /* We definitely have a new thread */
            __thread_inited = false;
            /* We might even have a new process */
            __process_inited = !(flags & CLONE_THREAD);
            maybe_init_thread();
        } else {
            /* Success; parent */
            if (flags & CLONE_VFORK) {
                prov_log_set_enabled(was_prov_log_enabled);
            }
            if (likely(prov_log_is_enabled())) {
                op.data.clone.child_process_id = (flags & CLONE_THREAD) ? getpid() : ret;
                op.data.clone.child_thread_id = ret;
                prov_log_record(op);
            }
        }
   });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Process-Completion.html */
pid_t waitpid (pid_t pid, int *status_ptr, int options) { }
pid_t wait (int *status_ptr) { }
pid_t wait4 (pid_t pid, int *status_ptr, int options, struct rusage *usage) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/BSD-Wait-Functions.html */
pid_t wait3 (int *status_ptr, int options, struct rusage *usage) { }

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
