/*
 * This file looks like C, but it is not read by the C compiler!
 * It is a place-holder for C code and is processed by gen_libprov.py and put into libprov_middle.c.
 * It reuses C's grammar, so I get syntax highlighting and I can parse it into fragments of C syntax easily.
 * Rationale: In this part of the project, there are many repetitions of code automatically generated.
 * For example, for each function $foo, we define a wrapper function $foo that calls the original function client_$foo with the same arguments.
 * Just read libprov_middle.c.
 * I can more easily refactor how it works if I don't have to edit each individual instance.
 * gen_libprov.py reads the function signatures, and inside the function bodies, it looks for some specific variable declarations of the form: Type var_name = var_val;
 * We use GCC block-expressions to communicate blocks of code to gen_libprov.py: ({stmt0; stmt1; ...; }).
 */

/* Need these typedefs to make pycparser parse the functions. They won't be used in libprov_middle.c */
typedef void* DIR;
typedef void* FILE;
typedef void* bool;
typedef void* dev_t;
typedef void* fn;
typedef void* ftw_func;
typedef void* gid_t;
typedef void* id_t;
typedef void* idtype;
typedef void* idtype_t;
typedef void* ino_t;
typedef void* int64_t;
typedef void* mode_t;
typedef void* nftw_func;
typedef void* off_t;
typedef void* pid_t;
typedef void* posix_spawn_file_actions_t;
typedef void* posix_spawnattr_t;
typedef void* pthread_attr_t;
typedef void* pthread_t;
typedef void* siginfo_t;
typedef void* size_t;
typedef void* ssize_t;
typedef void* suseconds_t;
typedef void* subseconds_t;
typedef void* thrd_start_t;
typedef void* thrd_t;
typedef void* time_t;
typedef void* uid_t;
typedef void* va_list;
typedef void* StringArray;
typedef void* OpenNumber;

int __type_mode_t;
typedef int (*fn_ptr_int_void_ptr)(void*);

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html */
FILE * fopen (const char *filename, const char *opentype) {
    void* call = ({
        FILE* ret = fopen_wrapper(filename, opentype);        
    });    
}
fn fopen64 = fopen;
FILE * freopen (const char *filename, const char *opentype, FILE *stream) {
    void* call = ({
        fclose(stream);
        FILE* ret = fopen_wrapper(filename, opentype);        
    });
}
fn freopen64 = freopen;

/* Need: In case an analysis wants to use open-to-close consistency */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html */
int fclose (FILE *stream) {
    void* pre_call = ({ int fd = fileno(stream); });
    void* post_call = ({
        if (LIKELY(ret == 0 && prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .close_tag = OpData_Close,
                    .close = {.open_number = reset_open_number(fd)},
                },
                .ferrno = 0,
            });
            reset_open_number(fd);
        }
    });
}
int fcloseall(void) {
    void* call = ({
        /* TODO: We are also technically supposed to flush the streams here. */
        closefrom(0);
        int ret = 0;
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/openat.2.html */
int openat(int dirfd, const char *filename, int flags, ...) {
    void* call = ({
        // Need explicit call because variadic arg
        mode_t mode = 0;
        if (((flags & O_CREAT) != 0) || ((flags & O_TMPFILE) == O_TMPFILE)) {
            va_list ap;
            va_start(ap, flags);
            mode = va_arg(ap, __type_mode_t);
            va_end(ap);
        }
        int ret = open_wrapper(dirfd, filename, flags, mode);
    });
}
fn openat64 = openat;

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html */
int open(const char* filename, int flags, ...) {
    void* call = ({
        mode_t mode = 0;
        if (((flags & O_CREAT) != 0) || ((flags & O_TMPFILE) == O_TMPFILE)) {
            va_list ap;
            va_start(ap, flags);
            mode = va_arg(ap, __type_mode_t);
            va_end(ap);
        }
        int ret = open_wrapper(AT_FDCWD, filename, flags, mode);
    });
}
int __openat_2(int fd, const char* file, int flags) {
    void* call = ({
        int ret = open_wrapper(fd, file, flags, 0);
    });
}
fn open64 = open;
int __open_2(const char* filename, int flags) {
    void* call = ({
        int ret = open_wrapper(AT_FDCWD, filename, flags, 0);
    });
}
fn __open64_2 = __open_2;
fn __openat64_2 = __openat_2;
int creat (const char *filename, mode_t mode) {
    void* call = ({
        int ret = open_wrapper(AT_FDCWD, filename, O_CREAT|O_WRONLY|O_TRUNC, mode);
    });
}
fn creat64 = creat;
int close (int filedes) {
    void* post_call = ({
        if (LIKELY(ret == 0 && prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .close_tag = OpData_Close,
                    .close = {.open_number = reset_open_number(filedes)},
                },
                .ferrno = 0,
            });
        }
    });
}
int close_range (unsigned int lowfd, unsigned int maxfd, int flags) {
    void* call = ({
        ASSERTF(flags == 0 || flags == CLOSE_RANGE_CLOEXEC,
                "I haven't implemented CLOSE_RANGE_UNSHARE");
        DIR* dp = EXPECT_NONNULL(client_opendir("/proc/self/fd"));
        struct dirent* dirp;
        DEBUG("close_range %d %d %d -> close", lowfd, maxfd, flags);
        while ((dirp = client_readdir(dp)) != NULL) {
            if (LIKELY('0' <= dirp->d_name[0] && dirp->d_name[0] <= '9')) {
                unsigned int fd = (unsigned int) my_atoui(dirp->d_name);
                if (lowfd <= fd && fd <= maxfd) {
                    /* Use the real (not client) close, so it gets logged as a normal close */
                    if (flags == 0) {
                        close(fd);
                    } else if (flags == CLOSE_RANGE_CLOEXEC) {
                        int fd_flags = fcntl(fd, F_GETFD);
                        fd_flags |= O_CLOEXEC;
                        fcntl(fd, F_SETFD, fd_flags);
                    }
                }
            }
        }
        client_closedir(dp);
        int ret = 0;
    });
}
void closefrom (int lowfd) {
    void* call = ({
        DIR* dp = EXPECT_NONNULL(client_opendir("/proc/self/fd"));
        struct dirent* dirp;
        DEBUG("closefrom %d -> close", lowfd);
        while ((dirp = client_readdir(dp)) != NULL) {
            if (LIKELY('0' <= dirp->d_name[0] && dirp->d_name[0] <= '9')) {
                int fd = (int) my_atoui(dirp->d_name);
                if (lowfd <= fd) {
                    /* Use the real (not client) close, so it gets logged as a normal close */
                    close(fd);
                }
            }
        }
        client_closedir(dp);
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Dup]licating-Descriptors.html */
int dup (int old) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled() && ret != -1)) {
            prov_log_record((struct Op) {
                .data = {
                    .dup_tag = OpData_Dup,
                    .dup = {dup_open_numbers(old, ret), 0},
                },
                .ferrno = 0,
            });
        }
    });
}
int dup2 (int old, int new) {
    void* call = ({
        int ret = dup3(old, new, 0);
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/dup.2.html */
int dup3 (int old, int new, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled() && ret != -1)) {
            prov_log_record((struct Op) {
                .data = {
                    .dup_tag = OpData_Dup,
                    .dup = {dup_open_numbers(old, new), 0},
                },
                .ferrno = 0,
            });
        }
    });
}

/* TODO: fcntl to op */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Control-Operations.html#index-fcntl-function */
int fcntl (int filedes, int command, ...) {
    void* pre_call = ({
            /* Parse args */

            bool has_int_arg = command == F_DUPFD || command == F_DUPFD_CLOEXEC || command == F_SETFD || command == F_SETFL || command == F_SETOWN || command == F_SETSIG || command == F_SETLEASE || command == F_NOTIFY || command == F_SETPIPE_SZ || command == F_ADD_SEALS;
            bool has_ptr_arg = command == F_SETLK || command == F_SETLKW || command == F_GETLK || command == F_OFD_SETLK || command == F_OFD_SETLKW || command == F_OFD_GETLK || command == F_GETOWN_EX || command == F_SETOWN_EX || command == F_GET_RW_HINT || command == F_SET_RW_HINT || command == F_GET_FILE_RW_HINT || command == F_SET_FILE_RW_HINT;
            /* Highlander assertion: there can only be one! */
            /* But there could be zero, as in fcntl(fd, F_GETFL) */
            ASSERTF(!has_int_arg || !has_ptr_arg, "");

            int int_arg = 0;
            void* ptr_arg = NULL;
            va_list ap;
            va_start(ap, command);
            if (has_int_arg) {
                int_arg = va_arg(ap, __type_int);
            } else if (has_ptr_arg) {
                ptr_arg = va_arg(ap, __type_voidp);
            }
            va_end(ap);
        });
    void* call = ({
        int ret;
        if (has_int_arg) {
            ret = client_fcntl(filedes, command, int_arg);
        } else if (has_ptr_arg) {
            ret = client_fcntl(filedes, command, ptr_arg);
        } else {
            ret = client_fcntl(filedes, command);
        }
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (LIKELY(ret == 0) && command == F_DUPFD || command == F_DUPFD_CLOEXEC) {
                prov_log_record((struct Op) {
                    .data = {
                        .dup_tag = OpData_Dup,
                        .dup = {
                            .old = get_open_number(filedes),
                            .flags = (command == F_DUPFD_CLOEXEC) ? O_CLOEXEC : 0,
                        },
                    },
                    .ferrno = 0,
                });
            }
        }
    });
}

/* Need: We need this so that opens relative to the current working directory can be resolved */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Working-Directory.html */
int chdir (const char *filename) {
    void* call = ({
        int ret;
        int fd = open(filename, O_PATH);
        if (fd > 0) {
            ret = fchdir(fd);
        } else {
            ret = -1;
        }
    });
}
int fchdir (int filedes) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled() && ret == 0)) {
            dup_open_numbers(filedes, AT_FDCWD);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Opening-a-Directory.html */
DIR * opendir (const char *dirname) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .open_tag = OpData_Open,
                    .open = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), dirname, PATH_MAX),
                        },
                        .open_number = {0},
                        .inode = {0},
                        .mode = 0,
                        /* https://github.com/esmil/musl/blob/master/src/dirent/opendir.c */
                        .flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
                        .dir = true,
                        .creat = false,
                    },
                },
                .ferrno = call_errno,
            };            
            if (LIKELY(ret != NULL)) {
                op.ferrno = 0;
                int fd = dirfd(ret);
                op.data.open.open_number = get_open_number(fd);
                op.data.open.inode = get_inode(fd);
            }
            prov_log_record(op);
        }
    });
}
DIR * fdopendir (int fd) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            OpenNumber on = get_open_number(fd);        
            struct Op op = {
                .data = {
                    .open_tag = OpData_Open,
                    .open = {
                        .path = {
                            .directory = on,
                            .name = NULL,
                        },
                        .open_number = on,
                        .inode = get_inode(fd),
                        .mode = 0,
                        /* https://github.com/esmil/musl/blob/master/src/dirent/opendir.c */
                        .flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
                        .dir = true,
                        .creat = false,
                    },
                },
                .ferrno = UNLIKELY(ret == NULL) ? call_errno : 0,
            };
            prov_log_record(op);
        }
    });
}

/* TODO: interpose and sort dirent iteration */
/* https://www.gnu.org/software/libc/manual/html_node/Reading_002fClosing-Directory.html */
struct dirent * readdir (DIR *dirstream) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            int fd = dirfd(dirstream);
            struct Op op = {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(fd),
                            .name = NULL,
                        },
                        .child = NULL,
                        .all_children = false,
                    },
                },
                .ferrno = call_errno,
            };
            if (LIKELY(ret != NULL)) {
                /* Note: we will assume these dirents are the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.ferrno = 0;
                op.data.readdir.child = arena_strndup(get_data_arena(), ret->d_name, sizeof(ret->d_name));
            }
            prov_log_record(op);
        }
    });
}
struct dirent64 * readdir64 (DIR *dirstream) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(dirfd(dirstream)),
                            .name = NULL,
                        },
                        .child = NULL,
                        .all_children = false,
                    },
                },
                .ferrno = call_errno,
            };
            if (LIKELY(ret != NULL)) {
                op.ferrno = 0;
                /* Note: we will assume these dirents are the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(get_data_arena(), ret->d_name, sizeof(ret->d_name));
            }
            prov_log_record(op);
        }
    });
}

int readdir_r (DIR *dirstream, struct dirent *entry, struct dirent **result) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(dirfd(dirstream)),
                            .name = NULL,
                        },
                        .child = NULL,
                        .all_children = false,
                    },
                },
                .ferrno = call_errno,
            };            
            if (LIKELY(*result != NULL)) {
                op.ferrno = 0;
                /* Note: we will assume these dirents are the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(get_data_arena(), entry->d_name, sizeof(entry->d_name));
            }
            prov_log_record(op);
        }
    });
}
int readdir64_r (DIR *dirstream, struct dirent64 *entry, struct dirent64 **result) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(dirfd(dirstream)),
                            .name = NULL,
                        },
                        .child = NULL,
                        .all_children = false,
                    },
                },
                .ferrno = call_errno,
            };
            if (LIKELY(*result != NULL)) {
                op.ferrno = 0;
                /* Note: we will assume these dirents are the same as openat(fd, ret->name);
                 * This is roughly, "the file-system implementation is self-consistent between readdir and openat."
                 * */
                op.data.readdir.child = arena_strndup(get_data_arena(), entry->d_name, sizeof(entry->d_name));
            }
            prov_log_record(op);
        }
    });
}

int closedir (DIR *dirstream) {
    void* pre_call = ({ int fd = dirfd(dirstream); });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled() && ret == 0)) {
            struct Op op = {
                .data = {
                    .close_tag = OpData_Close,
                    .close = {
                        .open_number = reset_open_number(fd)
                    },
                },
                .ferrno = 0,
            };
            reset_open_number(fd);
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
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), dir, PATH_MAX),
                        },
                        .child = NULL,
                        .all_children = true,
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno,
            });
        }
    });
}
int scandir64 (const char *dir, struct dirent64 ***namelist, int (*selector) (const struct dirent64 *), int (*cmp) (const struct dirent64 **, const struct dirent64 **)) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op){
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), dir, PATH_MAX),
                        },
                        .child = NULL,
                        .all_children = true,
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno,
            });
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man3/scandir.3.html */
int scandirat(int dir_fd, const char *restrict dirp,
            struct dirent ***restrict namelist,
            int (*filter)(const struct dirent *),
            int (*compar)(const struct dirent **, const struct dirent **)) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(dir_fd),
                            .name = arena_strndup(get_data_arena(), dirp, PATH_MAX),
                        },
                        .child = NULL,
                        .all_children = true,
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno,
            });
        }
    });
}

/* https://www.gnu.org/software/libc/manual/html_node/Low_002dlevel-Directory-Access.html */
ssize_t getdents64 (int fd, void *buffer, size_t length) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(fd),
                            .name = NULL,
                        },
                        .child = NULL,
                        .all_children = true,
                    },
                },
                .ferrno = UNLIKELY(ret == -1) ? call_errno : 0
            });
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Working-with-Directory-Trees.html */
/* Need: These operations walk a directory recursively */
int ftw (const char *filename, ftw_func func, int descriptors) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                        },
                        .child = NULL,
                        .all_children = true,
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno,
            });
        }
    });
}
int nftw (const char *filename, nftw_func func, int descriptors, int flag) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .readdir_tag = OpData_Readdir,
                    .readdir = {
                        .dir = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                        },
                        .child = NULL,
                        .all_children = true,
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            });
        }
    });
}
/* I can't include ftw.h on some systems because it defines fstatat as extern int on some machines. */

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Hard-Links.html */
int link (const char *oldname, const char *newname) {
    void* call = ({
        int ret = linkat(AT_FDCWD, oldname, AT_FDCWD, newname, 0);
    });
}
int linkat (int oldfd, const char *oldname, int newfd, const char *newname, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .hard_link_tag = OpData_HardLink,
                    .hard_link = {
                        .old = {
                            .directory = get_open_number(oldfd),
                            .name = arena_strndup(get_data_arena(), oldname, PATH_MAX),
                        },
                        .new_ = {
                            .directory = get_open_number(newfd),
                            .name = arena_strndup(get_data_arena(), newname, PATH_MAX),
                        },
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno,
            });
        }
    });
}

/* TODO: debug */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html */
int symlink (const char *oldname, const char *newname) {
    void* call = ({
        int ret = symlinkat(oldname, AT_FDCWD, newname);
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/symlink.2.html */
int symlinkat(const char *target, int newdirfd, const char *linkpath) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .symbolic_link_tag = OpData_SymbolicLink,
                    .symbolic_link = {
                        .old = arena_strndup(get_data_arena(), target, PATH_MAX),
                        .new_ = {
                            .directory = get_open_number(newdirfd),
                            .name = arena_strndup(get_data_arena(), linkpath, PATH_MAX),
                        },
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            });
        }
    });
}

/* TODO */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html */
ssize_t readlink (const char *filename, char *buffer, size_t size) {
    void* call = ({
        ssize_t ret = readlinkat(AT_FDCWD, filename, buffer, size);
    });
}
ssize_t readlinkat (int dir_fd, const char *filename, char *buffer, size_t size) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .read_link_tag = OpData_ReadLink,
                    .read_link = {
                        .linkpath = {
                            .directory = get_open_number(dir_fd),
                            .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                        },
                        .referent = NULL,
                        .truncation = false,
                        .recursive_dereference = false,
                    },
                },
                .ferrno = call_errno,
            };            
            if (LIKELY(ret != -1)) {
                op.ferrno = 0;
                op.data.read_link.referent = arena_strndup(get_data_arena(), buffer, ret + 1);
                ((char*)op.data.read_link.referent)[ret] = '\0';
                // If the returned value equals bufsiz, then truncation may have occurred.
                op.data.read_link.truncation = ((size_t) ret) == size;
            }
            prov_log_record(op);
        }
    });
}
char * canonicalize_file_name (const char *name) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .read_link_tag = OpData_ReadLink,
                    .read_link = {
                        .linkpath = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), name, PATH_MAX),
                        },
                        .referent = NULL,
                        .truncation = false,
                        .recursive_dereference = true,
                    },
                },
                .ferrno = call_errno,
            };
            if (LIKELY(ret)) {
                op.ferrno = 0;
                op.data.read_link.referent = arena_strndup(get_data_arena(), ret, PATH_MAX);
                op.data.read_link.truncation = false;
            }
            prov_log_record(op);
        }
    });
}
char * realpath (const char *restrict name, char *restrict resolved) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .read_link_tag = OpData_ReadLink,
                    .read_link = {
                        .linkpath = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), name, PATH_MAX),
                        },
                        .referent = NULL,
                        .truncation = false,
                        .recursive_dereference = true,
                    },
                },
                .ferrno = call_errno,
            };
            if (LIKELY(ret)) {
                op.ferrno = 0;
                op.data.read_link.referent = arena_strndup(get_data_arena(), ret, PATH_MAX);
                op.data.read_link.truncation = false;
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Deleting-Files.html */
int rmdir (const char *filename) {
    void* call = ({
        int ret = remove(filename);
    });
}
int remove (const char *filename) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .unlink_tag = OpData_Unlink,
                    .unlink = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                        },
                        .unlink_type = 2,
                    },
                },
                .ferrno = UNLIKELY(ret == -1) ? call_errno : 0
            });
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/unlink.2.html */
int unlink (const char *filename) {
    void* call = ({
        int ret = unlinkat(AT_FDCWD, filename, 0);
    });
}
int unlinkat(int dirfd, const char *pathname, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .unlink_tag = OpData_Unlink,
                    .unlink = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), pathname, PATH_MAX),
                        },
                        .unlink_type = 0,
                    },
                },
                .ferrno = UNLIKELY(ret == -1) ? call_errno : 0
            });
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Renaming-Files.html */
int rename (const char *oldname, const char *newname) {
    void* call = ({
        int ret = renameat2(AT_FDCWD, oldname, AT_FDCWD, newname, 0);
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/rename.2.html */
int renameat(int olddirfd, const char *oldpath,
           int newdirfd, const char *newpath) {
    void* call = ({
        int ret = renameat2(olddirfd, oldpath, newdirfd, newpath, 0);
    });
}
int renameat2(int olddirfd, const char *oldpath,
            int newdirfd, const char *newpath, unsigned int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .rename_tag = OpData_Rename,
                    .rename = {
                        .src = {
                            .directory = get_open_number(olddirfd),
                            .name = arena_strndup(get_data_arena(), oldpath, PATH_MAX),
                        },
                        .dst = {
                            .directory = get_open_number(newdirfd),
                            .name = arena_strndup(get_data_arena(), newpath, PATH_MAX),
                        },
                    },
                },
                .ferrno = UNLIKELY(ret == -1) ? call_errno : 0
            });
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Creating-Directories.html */
int mkdir(const char* filename, mode_t mode) {
    void* call = ({
        int ret = mkdirat(AT_FDCWD, filename, mode);
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/mkdirat.2.html */
int mkdirat(int dirfd, const char *pathname, mode_t mode) {
    void* post_call = ({
        prov_log_record((struct Op) {
            .data = {
                .mk_file_tag = OpData_MkFile,
                .mk_file = {
                    .path = {
                        .directory = get_open_number(dirfd),
                        .name = arena_strndup(get_data_arena(), pathname, PATH_MAX),
                    },
                    .file_type = FileType_Dir,
                },
            },
            .ferrno = UNLIKELY(ret == -1) ? call_errno : 0,
        });
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Reading-Attributes.html */
int stat (const char *filename, struct stat *buf) {
    void* call = ({
        int ret = fstatat(AT_FDCWD, filename, buf, 0);
    });
}
int fstat (int filedes, struct stat *buf) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .stat_tag = OpData_Stat,
                    .stat = {
                        .path = {
                            .directory = get_open_number(filedes),
                            .name = NULL,
                        },
                        .flags = 0,
                        .stat_result = {0},
                    },
                },
                .ferrno = call_errno,
            };
            if (LIKELY(ret == 0)) {
                op.ferrno = 0;
                stat_result_from_stat(&op.data.stat.stat_result, buf);
            }
            prov_log_record(op);
        }
    });
}
int lstat (const char *filename, struct stat *buf) {
    void* call = ({
        int ret = fstatat(AT_FDCWD, filename, buf, AT_SYMLINK_NOFOLLOW);
    });
}
fn newfstatat = fstatat;
/* Docs: https://linux.die.net/man/2/fstatat */
int fstatat(int dirfd, const char * restrict pathname, struct stat * restrict buf, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .stat_tag = OpData_Stat,
                    .stat = {
                        .path = {
                            .directory = get_open_number(dirfd),
                            .name = arena_strndup(get_data_arena(), pathname, PATH_MAX),
                        },
                        .flags = flags,
                        .stat_result = {0},
                    },
                },
                .ferrno = call_errno,
            };
            if (LIKELY(ret == 0)) {
                op.ferrno = 0;
                stat_result_from_stat(&op.data.stat.stat_result, buf);
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/statx.2.html */
int statx(int dirfd, const char *restrict pathname, int flags, unsigned int mask, struct statx *restrict statxbuf) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .stat_tag = OpData_Stat,
                    .stat = {
                        .path = {
                            .directory = get_open_number(dirfd),
                            .name = arena_strndup(get_data_arena(), pathname, PATH_MAX),
                        },
                        .flags = flags,
                        .stat_result = {0},
                    },
                },
                .ferrno = call_errno,
            };
            if (LIKELY(ret == 0)) {
                op.ferrno = 0;
                stat_result_from_statx(&op.data.stat.stat_result, statxbuf);
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/File-Owner.html */
int chown (const char *filename, uid_t owner, gid_t group) {
    void* call = ({
        int ret = fchownat(AT_FDCWD, filename, owner, group, 0);
    });
}
int fchown (int filedes, uid_t owner, gid_t group) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .update_metadata_tag = OpData_UpdateMetadata,
                    .update_metadata = {
                        .path = {
                            .directory = get_open_number(filedes),
                            .name = NULL,
                        },
                        .flags = 0,
                        .value = {
                            .ownership_tag = MetadataValue_Ownership,
                            .ownership = {
                                .uid = owner,
                                .gid = group,
                            },
                        },
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            });
        }
    });
}

// https://www.man7.org/linux/man-pages/man2/lchown.2.html
int lchown(const char *pathname, uid_t owner, gid_t group) {
    void* call = ({
        int ret = fchownat(AT_FDCWD, pathname, owner, group, AT_SYMLINK_NOFOLLOW);
    });
}
int fchownat(int dirfd, const char *pathname, uid_t owner, gid_t group, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .update_metadata_tag = OpData_UpdateMetadata,
                    .update_metadata = {
                        .path = {
                            .directory = get_open_number(dirfd),
                            .name = arena_strndup(get_data_arena(), pathname, PATH_MAX),
                        },
                        .flags = flags,
                        .value = {
                            .ownership_tag = MetadataValue_Ownership,
                            .ownership = {
                                .uid = owner,
                                .gid = group,
                            },
                        },
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno,
            });
        }
    });
}


/* Docs: https://www.gnu.org/software/libc/manual/html_node/Setting-Permissions.html  */
int chmod (const char *filename, mode_t mode) {
    void* call = ({
        int ret = fchmodat(AT_FDCWD, filename, mode, 0);
    });
}
int fchmod (int filedes, mode_t mode) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .update_metadata_tag = OpData_UpdateMetadata,
                    .update_metadata = {
                        .path = {
                            .directory = get_open_number(filedes),
                            .name = NULL,
                        },
                        .flags = 0,
                        .value = {
                            .mode_tag = MetadataValue_Mode,
                            .mode = {mode},
                        },
                    }
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            });
        }
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/chmod.2.html */
int fchmodat(int dirfd, const char *pathname, mode_t mode, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .update_metadata_tag = OpData_UpdateMetadata,
                    .update_metadata = {
                        .path = {
                            .directory = get_open_number(dirfd),
                            .name = arena_strndup(get_data_arena(), pathname, PATH_MAX),
                        },
                        .flags = flags,
                        .value = {
                            .mode_tag = MetadataValue_Mode,
                            .mode = {mode},
                        },
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            });
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Testing-File-Access.html */
int access (const char *filename, int how) {
    void* call = ({
        int ret = faccessat(AT_FDCWD, filename, how, 0);
    });
}

/* Docs: https://www.man7.org/linux/man-pages/man3/faccessat.3p.html */
int faccessat(int dirfd, const char *pathname, int mode, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record((struct Op) {
                .data = {
                    .access_tag = OpData_Access,
                    .access = {
                        .path = {
                            .directory = get_open_number(dirfd),
                            .name = arena_strndup(get_data_arena(), pathname, PATH_MAX),
                        },
                        .mode = mode,
                        .flags = flags,
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            });
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/File-Times.html */
int utime (const char *filename, const struct utimbuf *times) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .update_metadata_tag = OpData_UpdateMetadata,
                    .update_metadata = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                        },
                        .flags = 0,
                        .value = {
                            .times_tag = MetadataValue_Times,
                            .times = {0},
                        },
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            };
            if (times) {
                op.data.update_metadata.value.times.is_null = false;
                op.data.update_metadata.value.times.atime.tv_sec = times->actime;
                op.data.update_metadata.value.times.mtime.tv_sec = times->modtime;
            } else {
                op.data.update_metadata.value.times.is_null = true;
            }
            prov_log_record(op);
        }
    });
}
int utimes (const char *filename, const struct timeval tvp[2]) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .update_metadata_tag = OpData_UpdateMetadata,
                    .update_metadata = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                        },
                        .flags = 0,
                        .value = {
                            .times_tag = MetadataValue_Times,
                            .times = {0},
                        },
                    },
                },
            };
            if (tvp) {
                op.data.update_metadata.value.times.is_null = false;
                op.data.update_metadata.value.times.atime = *(struct TimeVal*)&tvp[0];
                op.data.update_metadata.value.times.mtime = *(struct TimeVal*)&tvp[1];
            } else {
                op.data.update_metadata.value.times.is_null = true;
            }
            op.ferrno = LIKELY(ret == 0) ? 0 : call_errno;
            prov_log_record(op);
        }
    });
}
int lutimes (const char *filename, const struct timeval tvp[2]) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .update_metadata_tag = OpData_UpdateMetadata,
                    .update_metadata = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                        },
                        .flags = AT_SYMLINK_NOFOLLOW,
                        .value = {
                            .times_tag = MetadataValue_Times,
                            .times = {0},
                        },
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            };
            if (tvp) {
                op.data.update_metadata.value.times.is_null = false;
                op.data.update_metadata.value.times.atime = *(struct TimeVal*)&tvp[0];
                op.data.update_metadata.value.times.mtime = *(struct TimeVal*)&tvp[1];
            } else {
                op.data.update_metadata.value.times.is_null = true;
            }
            prov_log_record(op);
        }
    });
}
int futimes (int fd, const struct timeval tvp[2]) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            struct Op op = {
                .data = {
                    .update_metadata_tag = OpData_UpdateMetadata,
                    .update_metadata = {
                        .path = {
                            .directory = get_open_number(fd),
                            .name = NULL,
                        },
                        .flags = AT_EMPTY_PATH,
                        .value = {
                            .times_tag = MetadataValue_Times,
                            .times = {0},
                        },
                    },
                },
                .ferrno = LIKELY(ret == 0) ? 0 : call_errno
            };
            if (tvp) {
                op.data.update_metadata.value.times.is_null = false;
                op.data.update_metadata.value.times.atime = *(struct TimeVal*)&tvp[0];
                op.data.update_metadata.value.times.mtime = *(struct TimeVal*)&tvp[1];
            } else {
                op.data.update_metadata.value.times.is_null = true;
            }
            prov_log_record(op);
        }
    });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/File-Size.html */
int truncate (const char *filename, off_t length) { }
int ftruncate (int fd, off_t length) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Making-Special-Files.html */
int mknod (const char *filename, mode_t mode, dev_t dev) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Temporary-Files.html */
FILE * tmpfile (void) { }
fn tmpfile64 = tmpfile;
char * tmpnam (char c[__PROBE_L_tmpnam]) { }
char * tmpnam_r (char c[__PROBE_L_tmpnam]) { }
char * tempnam (const char *dir, const char *prefix) { }
char * mktemp (char *template) { }
char * mkdtemp (char *template) { }

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Executing-a-File.html */
/* Need: We need this because exec kills all global variables, we need to dump our tables before continuing */
int execv (const char *filename, char *const argv[]) {
    void* pre_call = ({
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, 0);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)environ, &envc);
        /* TODO: Avoid this copy */
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, envc);
        struct Op op = {
            .data = {
                .exec_tag = OpData_Exec,
                .exec = {
                    .path = {
                        .directory = get_open_number(AT_FDCWD),
                        .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                    },
                    .argv = copied_argv,
                    .env = copied_updated_env,
                },
            },
            .ferrno = 0,
        };
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record(op);
        }
        prov_log_save();
    });
    void* call = ({
        int ret = client_execvpe(filename, argv, (char* const*)updated_env);
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
        free((char**) updated_env);
        if (LIKELY(prov_log_is_enabled())) {
            ASSERTF(call_errno > 0, "exec should only return if error");
            op.ferrno = call_errno;
            prov_log_record(op);
        }
    });
}
int execl (const char *filename, const char *arg0, ...) {
    void* pre_call = ({
        size_t argc = COUNT_NONNULL_VARARGS(arg0);
        char** argv = EXPECT_NONNULL(malloc((argc + 1) * sizeof(char*)));
        va_list ap;
        va_start(ap, arg0);
        for (size_t i = 0; i < argc; ++i) {
            argv[i] = va_arg(ap, __type_charp);
        }
        va_end(ap);
        argv[argc] = NULL;
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, argc);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)environ, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, envc);
        struct Op op = {
            .data = {
                .exec_tag = OpData_Exec,
                .exec = {
                    .path = {
                        .directory = get_open_number(AT_FDCWD),
                        .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                    },
                    .argv = copied_argv,
                    .env = copied_updated_env,
                },
            },
            .ferrno = 0,
        };
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record(op);
        }
        prov_log_save();
    });
    void* call = ({
        int ret = client_execvpe(filename, argv, (char* const*)updated_env);
    });
    void* post_call = ({
        free((char**) updated_env);
        free((char**) argv);
        if (LIKELY(prov_log_is_enabled())) {
            ASSERTF(call_errno > 0, "exec should only return if error");
            op.ferrno = call_errno;
            prov_log_record(op);
        }
    });
}
int execve (const char *filename, char *const argv[], char *const env[]) {
    void* pre_call = ({
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, 0);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)env, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, envc);
        struct Op op = {
            .data = {
                .exec_tag = OpData_Exec,
                .exec = {
                    .path = {
                        .directory = get_open_number(AT_FDCWD),
                        .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                    },
                    .argv = copied_argv,
                    .env = copied_updated_env,
                },
            },
            .ferrno = 0,
        };
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record(op);
        }
        prov_log_save();
    });
    void* call = ({
        int ret = client_execvpe(filename, argv, (char* const*)updated_env);
    });
    void* post_call = ({
        free((char**) updated_env);
        if (LIKELY(prov_log_is_enabled())) {
            ASSERTF(call_errno > 0, "exec should only return if error");
            op.ferrno = call_errno;
            prov_log_record(op);
        }
    });
}
int fexecve (int fd, char *const argv[], char *const env[]) {
    void* pre_call = ({
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, 0);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)env, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, 0);
        struct Op op = {
            .data = {
                .exec_tag = OpData_Exec,
                .exec = {
                    .path = {
                        .directory = get_open_number(fd),
                        .name = NULL,
                    },
                    .argv = copied_argv,
                    .env = copied_updated_env,
                },
            },
        };
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record(op);
        }
        prov_log_save();
    });
    void* call = ({
        int ret = client_fexecve(fd, argv, (char* const*)updated_env);
    });
    void* post_call = ({
        free((char**) updated_env);
        if (LIKELY(prov_log_is_enabled())) {
            ASSERTF(call_errno > 0, "exec should only return if error");
            op.ferrno = call_errno;
            prov_log_record(op);
        }
    });
}
int execle (const char *filename, const char *arg0, ...) {
    void* pre_call = ({
        size_t argc = COUNT_NONNULL_VARARGS(arg0);
        char** argv = EXPECT_NONNULL(malloc((argc + 1) * sizeof(char*)));
        va_list ap;
        va_start(ap, arg0);
        for (size_t i = 0; i < argc; ++i) {
            argv[i] = va_arg(ap, __type_charp);
        }
        argv[argc] = NULL;
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, argc);
        char** env = va_arg(ap, __type_charpp);
        va_end(ap);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)env, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, envc);
        struct Op op = {
            .data = {
                .exec_tag = OpData_Exec,
                .exec = {
                    .path = {
                        .directory = get_open_number(AT_FDCWD),
                        .name = arena_strndup(get_data_arena(), filename, PATH_MAX),
                    },
                    .argv = copied_argv,
                    .env = copied_updated_env,
                },
            },
            .ferrno = 0,
        };
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record(op);
        }
        prov_log_save();
        ERROR("Not implemented; I need to figure out how to update the environment.");
    });
    void* call = ({
        int ret = client_execvpe(filename, argv, (char* const*)updated_env);
    });
    void* post_call = ({
        free((char**)updated_env);
        free((char**)argv);
        if (LIKELY(prov_log_is_enabled())) {
            ASSERTF(call_errno > 0, "exec should only return if error");
            op.ferrno = call_errno;
            prov_log_record(op);
        }
    });
}
int execvp (const char *filename, char *const argv[]) {
    void* pre_call = ({
        const char* bin_path;
        if (filename[0] != '/') {
            char* tmp_bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
            lookup_on_path(filename, tmp_bin_path);
            bin_path = tmp_bin_path;
        } else {
            bin_path = filename;
        }
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, 0);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)environ, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, envc);
        struct Op op = {
            .data = {
                .exec_tag = OpData_Exec,
                .exec = {
                    .path = {
                        .directory = get_open_number(AT_FDCWD),
                        .name = arena_strndup(get_data_arena(), bin_path, PATH_MAX),
                    },
                    .argv = copied_argv,
                    .env = copied_updated_env,
                },
            },
            .ferrno = 0,
        };
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record(op);
        }
        prov_log_save();
    });
    void* call = ({
        int ret = client_execvpe(filename, argv, (char* const*)updated_env);
    });
    void* post_call = ({
        free((char**) updated_env);
        if (LIKELY(prov_log_is_enabled())) {
            ASSERTF(call_errno > 0, "exec should only return if error");
            op.ferrno = call_errno;
            prov_log_record(op);
        }
    });
}
int execlp (const char *filename, const char *arg0, ...) {
    void* pre_call = ({
        const char* bin_path = NULL;
        if (filename[0] != '/') {
            char* tmp_bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
            lookup_on_path(filename, tmp_bin_path);
            bin_path = tmp_bin_path;
        } else {
            bin_path = filename;
        }
        size_t argc = COUNT_NONNULL_VARARGS(arg0);
        char** argv = EXPECT_NONNULL(malloc((argc + 1) * sizeof(char*)));
        va_list ap;
        va_start(ap, arg0);
        for (size_t i = 0; i < argc; ++i) {
            argv[i] = va_arg(ap, __type_charp);
        }
        argv[argc] = NULL;
        va_end(ap);
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, argc);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)environ, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, envc);
        struct Op op = {
            .data = {
                .exec_tag = OpData_Exec,
                .exec = {
                    .path = {
                        .directory = get_open_number(AT_FDCWD),
                        .name = arena_strndup(get_data_arena(), bin_path, PATH_MAX),
                    },
                    .argv = copied_argv,
                    .env = copied_updated_env,
                },
            },
            .ferrno = 0,
        };
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record(op);
        }
        prov_log_save();
    });
    void* call = ({
        int ret = client_execvpe(filename, argv, (char**)updated_env);
    });
    void* post_call = ({
        free((char**) updated_env);
        free((char**) argv);
        if (LIKELY(prov_log_is_enabled())) {
            ASSERTF(call_errno > 0, "exec should only return if error");
            op.ferrno = call_errno;
            prov_log_record(op);
        }
    });
}

/* Docs: https://linux.die.net/man/3/execvpe1 */
int execvpe(const char *filename, char *const argv[], char *const envp[]) {
    void* pre_call = ({
        const char* bin_path = NULL;
        if (filename[0] != '/') {
            char* tmp_bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
            lookup_on_path(filename, tmp_bin_path);
            bin_path = tmp_bin_path;
        } else {
            bin_path = filename;
        }
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, 0);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)envp, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, envc);
        struct Op op = {
            .data = {
                .exec_tag = OpData_Exec,
                .exec = {
                    .path = {
                        .directory = get_open_number(AT_FDCWD),
                        .name = arena_strndup(get_data_arena(), bin_path, PATH_MAX),
                    },
                    .argv = copied_argv,
                    .env = copied_updated_env,
                },
            },
        };
        if (LIKELY(prov_log_is_enabled())) {
            prov_log_record(op);
        }
        prov_log_save();
    });
    void* call = ({
        int ret = client_execvpe(filename, argv, (char**)updated_env);
    });
    void* post_call = ({
        // This is our own malloc from update_env_with_probe_vars, so it should be safe to free
        free((char**) updated_env);
        if (LIKELY(prov_log_is_enabled())) {
            ASSERTF(call_errno > 0, "exec should only return if error");
            op.ferrno = call_errno;
            prov_log_record(op);
        }
    });
}


int posix_spawn(pid_t* restrict pid, const char* restrict path,
                const posix_spawn_file_actions_t* restrict file_actions,
                const posix_spawnattr_t* restrict attrp, char* const argv[restrict],
                char* const envp[restrict]) {
    void* pre_call = ({
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, 0);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)envp, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), (StringArray)updated_env, envc);

        struct Op spawn_op = {
            .data = {
                .spawn_tag = OpData_Spawn,
                .spawn = {
                    .exec = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), path, PATH_MAX),
                        },
                        .argv = copied_argv,
                        .env = copied_updated_env,
                    },
                    .child_pid = 0,
                },
            },
        };
    });
    void* call = ({
        int ret = client_posix_spawn(pid, path, file_actions, attrp, argv, (char**)updated_env);
    });
    void* post_call = ({
        if (UNLIKELY(ret != 0)) {
            spawn_op.ferrno = call_errno;
        } else {
            spawn_op.ferrno = 0;
            spawn_op.data.spawn.child_pid = *pid;
        }
        prov_log_record(spawn_op);
        free((char**) updated_env); // This is our own malloc from update_env_with_probe_vars, so it should be safe to free
    });
}

int posix_spawnp(pid_t* restrict pid, const char* restrict file,
                 const posix_spawn_file_actions_t* restrict file_actions,
                 const posix_spawnattr_t* restrict attrp, char* const argv[restrict],
                 char* const envp[restrict]) {
    void* pre_call = ({
        const char* bin_path = NULL;
        if (file[0] != '/') {
            char* tmp_bin_path = arena_calloc(get_data_arena(), PATH_MAX + 1, sizeof(char));
            lookup_on_path(file, tmp_bin_path);
            bin_path = tmp_bin_path;
        } else {
            bin_path = file;
        }
        StringArray copied_argv = arena_copy_argv(get_data_arena(), (StringArray)argv, 0);
        size_t envc = 0;
        StringArray updated_env = update_env_with_probe_vars((StringArray)envp, &envc);
        StringArray copied_updated_env = arena_copy_argv(get_data_arena(), updated_env, envc);

        struct Op spawn_op = {
            .data = {
                .spawn_tag = OpData_Spawn,
                .spawn = {
                    .exec = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), bin_path, PATH_MAX),
                        },
                        .argv = copied_argv,
                        .env = copied_updated_env,
                    },
                    .child_pid = 0,
                }
            },
        };
    });
    void* call = ({
        int ret = client_posix_spawnp(pid, file, file_actions, attrp, argv, (char**)updated_env);
    });
    void* post_call = ({
        if (UNLIKELY(ret != 0)) {
            spawn_op.ferrno = call_errno;
        } else {
            spawn_op.ferrno = 0;
            spawn_op.data.spawn.child_pid = *pid;
        }
        prov_log_record(spawn_op);
        free((char**) updated_env); // This is our own malloc from update_env_with_probe_vars, so it should be safe to free
    });
}

/* Need: Fork does copy-on-write, so we want to deduplicate our structures first */
/* Docs: https://www.gnu.org/software/libc/manual/html_node/Creating-a-Process.html */
pid_t fork (void) {
    void* pre_call = ({
        struct Op op = {
            .data = {
                .clone_tag = OpData_Clone,
                 .clone = {
                    /* As far as I can tell, fork has the same semantics as calling clone with flags == 0.
                     * I could be wrong.
                     * */
                    .flags = 0,
                    .run_pthread_atfork_handlers = true,
                    .task_type = TaskType_Pid,
                },
            },
        };
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (UNLIKELY(ret == -1)) {
                /* Failure */
                op.ferrno = call_errno;
                prov_log_record(op);
            } else if (ret == 0) {
                /* Success; child */
                init_after_fork();
            } else {
                /* Success; parent */
                op.ferrno = 0;
                op.data.clone.task_id = ret;
                prov_log_record(op);
            }
        }
    });
}
pid_t _Fork (void) {
     void* pre_call = ({
        struct Op op = {
            .data = {
                .clone_tag = OpData_Clone,
                .clone = {
                    /* As far as I can tell, fork has the same semantics as calling clone with flags == 0.
                     * I could be wrong.
                     * */
                    .flags = 0,
                    .run_pthread_atfork_handlers = false,
                    .task_type = TaskType_Pid,
                    .task_id = -1,
                },
            },
        };
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (UNLIKELY(ret == -1)) {
                /* Failure */
                op.ferrno = call_errno;
                prov_log_record(op);
            } else if (ret == 0) {
                /* Success; child */
                init_after_fork();
            } else {
                /* Success; parent */
                op.ferrno = 0;
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
     *     client_code > wrapped_exec > real_exec
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
            .data = {
                .clone_tag = OpData_Clone,
                .clone = {
                    .flags = 0,
                    .run_pthread_atfork_handlers = true,
                    .task_type = TaskType_Pid,
                    .task_id = -1,
                },
            },
        };
    });
    void* call = ({
        int ret = client_fork();
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (UNLIKELY(ret == -1)) {
                /* Failure */
                op.ferrno = call_errno;
                prov_log_record(op);
            } else if (ret == 0) {
                /* Success; child */
                init_after_fork();
            } else {
                /* Success; parent */
                op.ferrno = 0;
                op.data.clone.task_id = ret;
                prov_log_record(op);
            }
        }
    });
}

/* Docs: https://man7.org/linux/man-pages/man2/clone.2.html */
/* It appears the params are required now, and perhaps they are only commented out for older systems
 *
 * > In Linux 2.4 and earlier, clone() does not take arguments
 * > parent_tid, tls, and child_tid.
 *
 * Also see source code (I think): https://www.man7.org/linux/man-pages/man2/clone.2.html
 * */
int clone(
    fn_ptr_int_void_ptr fn,
    void *stack,
    int flags,
    void * arg,
    ...
) {
    void* pre_call = ({
        // Disable vfork()
        // See vfork() for reasons.
        flags = flags &~CLONE_VFORK;

        va_list ap;
        va_start(ap, arg);
        pid_t * parent_tid = va_arg(ap, __type_voidp);
        void * tls = va_arg(ap, __type_voidp);
        pid_t * child_tid = va_arg(ap, __type_voidp);
        va_end(ap);


        if (UNLIKELY((!(flags & CLONE_FILES)) != (!(flags & CLONE_VM)))) {
            ERROR("PROBE does not support this type of cloning CLONE_FILES=%d CLONE_VM=%d. flags=%d", !!(flags & CLONE_FILES), !!(flags & CLONE_VM), flags);
        }
        
        struct Op op = {
            .data = {
                .clone_tag = OpData_Clone,
                .clone = {
                    /* As far as I can tell, fork has the same semantics as calling clone with flags == 0.
                     * I could be wrong.
                     * */
                    .flags = flags,
                    .run_pthread_atfork_handlers = false,
                    .task_type = (flags & CLONE_THREAD) ? TaskType_Tid : TaskType_Pid,
                    .task_id = -1,
                }
            },
        };
        if (LIKELY(prov_log_is_enabled())) {
            if ((flags & CLONE_THREAD) != (flags & CLONE_VM)) {
                NOT_IMPLEMENTED("I conflate cloning a new thread (resulting in a process with the same PID, new TID) with sharing the memory space. If CLONE_SIGHAND is set, then Linux asserts CLONE_THREAD == CLONE_VM; If it is not set and CLONE_THREAD != CLONE_VM, by a real application, I will consider disentangling the assumptions (required to support this combination).");
            }
        }
    });
    void* call = ({
        int ret = client_clone(fn, stack, flags, arg, parent_tid, tls, child_tid);
    });
    void* post_call = ({
        if (UNLIKELY(ret == -1)) {
            /* Failure */
            if (LIKELY(prov_log_is_enabled())) {
                op.ferrno = call_errno;
                prov_log_record(op);
            }
        } else if (ret == 0) {
            /* Success; child. */
            if (flags & CLONE_THREAD) {
                ensure_thread_initted();
            } else {
                init_after_fork();
            }
        } else {
            if (LIKELY(prov_log_is_enabled())) {
                /* Success; parent */
                op.ferrno = 0;
                op.data.clone.task_id = ret;
                prov_log_record(op);
            }
        }
   });
}

/* Docs: https://www.gnu.org/software/libc/manual/html_node/Process-Completion.html */
pid_t waitpid (pid_t pid, int *status_ptr, int options) {
    void* call = ({
        pid_t ret = wait4(pid, status_ptr, options, NULL);
    });
}
pid_t wait (int *status_ptr) {
    void* call = ({
        pid_t ret = wait4(-1, status_ptr, 0, NULL);
    });
}
pid_t wait3 (int *status_ptr, int options, struct rusage *usage) {
    void* call = ({
        pid_t ret = wait4(-1, status_ptr, options, usage);
    });
}
pid_t wait4 (pid_t pid, int *status_ptr, int options, struct rusage *usage) {
    void* pre_call = ({
        struct Op wait_op = {
            .data = {
                .wait_tag = OpData_Wait,
                .wait = {
                    .task_type = TaskType_Pid,
                    .task_id = -1,
                    .options = options,
                    .status = 0,
                    .usage = null_usage,
                },
            },
        };
        int real_status = 0;
        if (!status_ptr) {
            status_ptr = &real_status;
        }
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (UNLIKELY(ret == -1)) {
                wait_op.ferrno = call_errno;
            } else {
                wait_op.ferrno = 0;
                wait_op.data.wait.task_id = ret;
                wait_op.data.wait.status = status_ptr ? *status_ptr : real_status;
                if (usage) {
                    memcpy(&wait_op.data.wait.usage, usage, sizeof(struct rusage));
                }
            }
            prov_log_record(wait_op);
        }
   });
}

/* Docs: https://www.man7.org/linux/man-pages/man2/wait.2.html */
int waitid(idtype_t idtype, id_t id, siginfo_t *infop, int options) {
    void* pre_call = ({
        struct Op wait_op = {
            .data = {
                .wait_tag = OpData_Wait,
                .wait = {
                    .task_type = TaskType_Tid,
                    .task_id = -1,
                    .options = options,
                    .status = 0,
                    .cancelled = false,
                    .usage = null_usage,
                },
            },
        };
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (UNLIKELY(ret == -1)) {
                wait_op.ferrno = call_errno;
            } else {
                wait_op.ferrno = 0;
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
            .data = {
                .clone_tag = OpData_Clone,
                .clone = {
                    .flags = CLONE_FILES | CLONE_FS | CLONE_IO | CLONE_PARENT | CLONE_SIGHAND | CLONE_THREAD | CLONE_VM,
                    .task_type = TaskType_IsoCThread,
                    .task_id = -1,
                    .run_pthread_atfork_handlers = false,
                },
            },
        };
    });
    void* call = ({
        struct ThrdHelperArg* real_arg = EXPECT_NONNULL(malloc(sizeof(struct ThrdHelperArg)));
        real_arg->func = func;
        real_arg->arg = arg;
        int ret = client_thrd_create(thr, thrd_helper, &real_arg);
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (UNLIKELY(ret != thrd_success)) {
                /* Failure */
                op.ferrno = call_errno;
                prov_log_record(op);
            } else {
                /* Success; parent */
                op.ferrno = 0;
                op.data.clone.task_id = *((int64_t*)thr);
                prov_log_record(op);
            }
        }
   });
}

int thrd_join (thrd_t thr, int *res) {
    void *pre_call = ({
        int64_t thread_id = 0;
        probe_libc_memcpy(&thread_id, &thr, sizeof(thrd_t)); /* Avoid type punning! */
        struct Op op = {
            .data = {
                .wait_tag = OpData_Wait,
                .wait = {
                    .task_type = TaskType_IsoCThread,
                    .task_id = thread_id,
                    .options = 0,
                    .status = 0,
                },
            },
        };
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (UNLIKELY(ret != thrd_success)) {
                /* Failure */
                op.ferrno = call_errno;
                prov_log_record(op);
            } else {
                /* Success; parent */
                op.ferrno = 0;
                op.data.wait.status = *res;
                prov_log_record(op);
            }
        }
   });
}

thrd_t thrd_current( void ) { }

/* Docs: https://www.man7.org/linux/man-pages/man3/pthread_create.3.html */
int pthread_create(pthread_t *restrict thread,
                 const pthread_attr_t *restrict attr,
                 void *(*start_routine)(void *),
                 void *restrict arg) {
    void* pre_call = ({
        struct PthreadHelperArg* real_arg = EXPECT_NONNULL(malloc(sizeof(struct PthreadHelperArg)));
        real_arg->start_routine = start_routine;
        real_arg->pthread_id = increment_pthread_id();
        real_arg->arg = arg;
        struct Op op = {
            .data = {
                .clone_tag = OpData_Clone,
                .clone = {
                    .flags = CLONE_FILES | CLONE_FS | CLONE_IO | CLONE_PARENT | CLONE_SIGHAND | CLONE_THREAD | CLONE_VM,
                    .task_type = TaskType_Pthread,
                    .task_id = real_arg->pthread_id,
                    .run_pthread_atfork_handlers = false,
                },
            },
        };
    });
    void* call = ({
        int ret = client_pthread_create(thread, attr, pthread_helper, real_arg);
    });
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled())) {
            if (UNLIKELY(ret != 0)) {
                /* Failure */
                op.ferrno = call_errno;
                prov_log_record(op);
            } else {
                /* Success; parent */
                op.ferrno = 0;
                prov_log_record(op);
            }
        }
   });
}

void pthread_exit(void* inner_ret) {
    void* call = ({
        struct Op op = {
            .data = {.exit_thread_tag = OpData_ExitThread, .exit_thread = {0}},
        };
        prov_log_record(op);
        struct PthreadReturnVal* pthread_return_val = EXPECT_NONNULL(malloc(sizeof(struct PthreadReturnVal)));
        pthread_return_val->type_id = PTHREAD_RETURN_VAL_TYPE_ID;
        pthread_return_val->pthread_id = get_pthread_id();
        pthread_return_val->inner_ret = inner_ret;
        client_pthread_exit(pthread_return_val);
    });
    bool noreturn = true;
}

int pthread_join(pthread_t thread, void **pthread_return) {
    void* pre_call = ({
        void* uncasted_return = NULL;
        struct Op op = {
            .data = {
                .wait_tag = OpData_Wait,
                .wait = {
                    .task_type = TaskType_Pthread,
                    .task_id = 0,
                    .options = 0,
                    .status = 0,
                    .cancelled = false,
                },
            },
        };
    });
    void* call = ({
        int ret = client_pthread_join(thread, &uncasted_return);
    });
    void* post_call = ({
        if (UNLIKELY(ret != 0)) {
            /* Failure */
            if (LIKELY(prov_log_is_enabled())) {
                op.ferrno = call_errno;
                prov_log_record(op);
            }
        } else {
            /* Success; parent */
            struct PthreadReturnVal* pthread_return_val = uncasted_return;
            if (LIKELY(pthread_return_val->type_id == PTHREAD_RETURN_VAL_TYPE_ID)) {
                op.data.wait.task_id = pthread_return_val->pthread_id;
                if (pthread_return) {
                    *pthread_return = pthread_return_val->inner_ret;
                }
                free(pthread_return_val);
            } else {
                DEBUG("Somehow pthread return value was not the type I was expecting.");
                if (pthread_return) {
                    *pthread_return = uncasted_return;
                }
            }
            if (LIKELY(prov_log_is_enabled())) {
                if (UNLIKELY(uncasted_return == PTHREAD_CANCELED)) {
                    op.data.wait.cancelled = true;
                }
                op.ferrno = 0;
                prov_log_record(op);
            }
        }
   });
}

int pthread_cancel(pthread_t thread) {
    void* pre_call = ({
        DEBUG("pthread_cancel messes up the tracking of pthreads. Whoever joins this, won't know which thread they are joining.");
    });
}

/* TODO: Convert these to ops */
void* mmap(void* addr, size_t length, int prot, int flags, int fd, off_t offset) {}
int munmap(void* addr, size_t length) { }

int pipe(int pipefd[2]) {
    void* call = ({
        int ret = pipe2(pipefd, 0);
    });
}

int pipe2(int pipefd[2], int flags) {
    void* post_call = ({
        /* A successful pipe call is equivalent to two opens on a fifo file into specific FDs */
        if (LIKELY(ret == 0)) {
            struct Op open_read_end_op = {
                .data = {
                    .open_tag = OpData_Open,
                    .open = {
                        .path = {
                            .directory = new_open_number(pipefd[0]),
                            .name = NULL,
                        },
                        .inode = get_inode(pipefd[0]),
                        .flags = O_RDONLY,
                        .mode = 0,
                        .creat = true,
                        .dir = false,
                    },
                },
                .ferrno = 0,
            };
            struct Op open_write_end_op = {
                .data = {
                    .open_tag = OpData_Open,
                    .open = {
                        .path = {
                            .directory = new_open_number(pipefd[1]),
                            .name = NULL,
                        },
                        .flags = O_CREAT | O_TRUNC | O_WRONLY,
                        .mode = 0,
                        .dir = false,
                        .creat = true,
                    },
                },
                .ferrno = 0,
            };
            prov_log_record(open_read_end_op);
            prov_log_record(open_write_end_op);
        }
    });
}

int mkfifo(const char* pathname, mode_t mode) {
    void* call = ({
        int ret = mkfifoat(AT_FDCWD, pathname, mode);
    });
}

int mkfifoat(int fd, const char* pathname, mode_t mode) {
    void* post_call = ({
        if (call_errno == 0) {        
            prov_log_record((struct Op){
                .data = {
                    .open_tag = OpData_Open,
                    .open = {
                        .path = {
                            .directory = get_open_number(fd),
                            .name = arena_strndup(get_data_arena(), pathname, PATH_MAX),
                        },
                        .inode = get_inode(ret),
                        .flags = 0,
                        .mode = mode,
                    },
                },
                .ferrno = 0,
            });
        }
    });
}

// functions we're not interposing, but need for libprobe functionality
char* strerror(int errnum) { }
void exit(int status) {
    void* precall = ({
        struct Op op = {
            .data = {.exit_process_tag = OpData_ExitProcess, .exit_process = {status}},
            .ferrno = 0,
        };
        prov_log_record(op);
    });
    bool noreturn = true;
}

int mkstemp(char* template) {
    void* call = ({
        int ret = mkostemp(template, 0);
    });
}
int mkostemp(char *template, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled() && ret > 0)) {
            prov_log_record((struct Op) {
                .data = {
                    .open_tag = OpData_Open,
                    .open = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), template, PATH_MAX),
                        },
                        .inode = get_inode(ret),
                        .creat = true,
                        .dir = false,
                        .flags = O_RDWR | O_CREAT | O_EXCL | flags,
                        .mode = 0,
                    },
                },
            });
        }
    });
};
int mkstemps(char *template, int suffixlen) {
    void* call = ({
        int ret = mkostemps(template, suffixlen, 0);
    });
};
int mkostemps(char* template, int suffixlen, int flags) {
    void* post_call = ({
        if (LIKELY(prov_log_is_enabled() && ret > 0)) {
            prov_log_record((struct Op) {
                .data = {
                    .open_tag = OpData_Open,
                    .open = {
                        .path = {
                            .directory = get_open_number(AT_FDCWD),
                            .name = arena_strndup(get_data_arena(), template, PATH_MAX),
                        },
                        .inode = get_inode(ret),
                        .creat = true,
                        .dir = false,
                        .flags = O_RDWR | O_CREAT | O_EXCL | flags,
                        .mode = 0,
                    },
                },
            });
        }
    });
};

/*
TODO:

Reads and writes:
read
4 p(read|write)(|64)
8 p(read|write)v(|2|64|64v2)
1 copy_file_range
4 aio_(read|write)(|64)
2 lio_listio(|64)
https://sourceware.org/glibc/manual/2.41/html_node/Low_002dLevel-I_002fO.html

mmap, mmap64, munmap, shm_open, shm_unlink, memfd_create

File locks through fcntl
TODO: getcwd, getwd, chroot
getdents
glob, glob64
shm_open, shm_unlink, memfd_create
mount, umount
ioctl
popen, pclose
sysconf, pathconf, fpathconf, confstr
getent?
bind
socketpair
connect
send, recv, sendto, recvfrom
getnetbyname, getnetbyaddr, setnetent, getnetent, endnetent
time, clock_gettime, clock_getres, gettimeofday
clock_settiime, ntp_gettime, ntp_adjtime, adjtime, stime, settimeofday

Already counted:
dup, dup2, dup3
link
linkat
rewinddir, telldir, seekdir
symlink, symlinkat
readlink, readlinkat
canonicalize_file_name
realpath
unlink
rmdir
remove
rename
tmpfile, tmpfile64
tmpnam, tmpnam_r, tempnam
mktemp, mkstemp, mkdtemp
truncate, truncate64, ftruncate, ftruncate64
mknod

prctl(PR_SET_NAME) could be nice

https://github.com/bminor/glibc/blob/098e449df01cd1db950030c09af667a2ee039460/io/Versions#L117
Also, cpp tests/examples/cat.c | grep open

Possible:
https://www.gnu.org/software/libc/manual/html_node/Standard-Locales.html

Think about signal handling

https://www.gnu.org/software/libc/manual/html_node/Limits-on-Resources.html
https://www.gnu.org/software/libc/manual/html_node/Semaphores.html
https://www.gnu.org/software/libc/manual/html_node/Name-Service-Switch.html
https://www.gnu.org/software/libc/manual/html_node/Users-and-Groups.html
https://www.gnu.org/software/libc/manual/html_node/System-Management.html

 */
