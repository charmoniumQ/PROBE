#![feature(iter_intersperse)]
mod util;
mod strace_prov_logger;
mod prov_logger;
mod globals;

use strace_prov_logger::StraceProvLogger;
use prov_logger::{ProvLogger, CType, CPrimType, ArgType, CFuncSig, CFuncSigs};

#[macro_use]
extern crate ctor;
#[ctor]
static PROV_LOGGER: StraceProvLogger = StraceProvLogger::new(&CFUNC_SIGS);

fn fopen_parser(file: *const libc::FILE, filename: *const libc::c_char, opentype: *const libc::c_char) {
    let fd = libc::fileno(file);
    PROV_LOGGER.associate(file, fd);
    match (opentype.read() as char, opentype.offset(1).read() as char) {
        ('r', '\0') => PROV_LOGGER.open_read     (libc::AT_FDCWD, filename, fd),
        ('r', '+' ) => PROV_LOGGER.open_readwrite(libc::AT_FDCWD, filename, fd),
        ('w', '\0') => PROV_LOGGER.open_overwrite(libc::AT_FDCWD, filename, fd),
        // w+ creates or truncates a new file, so it does not need to be readwrite; just write
        // However, the fd can be read and written by different processes
        ('w', '+' ) => PROV_LOGGER.open_overwriteshared(libc::AT_FDCWD, filename, fd),
        ('a', '\0') => PROV_LOGGER.open_writepart(libc::AT_FDCWD, filename, fd),
        ('a', '+' ) => PROV_LOGGER.open_readwrite(libc::AT_FDCWD, filename, fd),
    };
}

fn open_parser(ret: libc::c_int, dirfd: libc::c_int, filename: *const libc::c_char, flags: libc::c_int) {
    if false {
    } else if (flags & libc::O_ACCMODE) == libc::O_RDWR {
        if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            // See comment on fopen w+
            PROV_LOGGER.open_overwriteshared(dirfd, filename, ret);
        } else {
            PROV_LOGGER.open_readwrite(dirfd, filename, ret);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_RDONLY {
        if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            // Truncates the file, which is a write
            // And then reads from it. Maybe someone else wrote to it since then.
            PROV_LOGGER.open_readwrite(dirfd, filename, ret);
        } else {
            PROV_LOGGER.open_read(dirfd, filename, ret);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_WRONLY {
        if flags & libc::O_TMPFILE != 0 {
            PROV_LOGGER.open_overwrite(dirfd, "$tmp" as *const libc::c_char, ret);
        } else if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            PROV_LOGGER.open_overwrite(dirfd, filename, ret);
        } else {
            PROV_LOGGER.open_writepart(dirfd, filename, ret);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_PATH {
        PROV_LOGGER.open_none(dirfd, filename, ret);
    }
}

extern crate project_specific_macros;
project_specific_macros::populate_libc_calls_and_hook_fns!{
    // https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html
    FILE * fopen (const char *filename, const char *opentype) {
        fopen_parser(call_return, filename, opentype);
    };
    FILE * fopen64 (const char *filename, const char *opentype) {
        fopen_parser(call_return, filename, opentype);
    };
    FILE * freopen (const char *filename, const char *opentype, FILE *stream) {
        PROV_LOGGER.fclose(stream);
        fopen_parser(stream, filename, opentype);
    };
    FILE * freopen64 (const char *filename, const char *opentype, FILE *stream) {
        PROV_LOGGER.fclose(stream);
        fopen_parser(stream, filename, opentype);
    };

    // We need these in case an analysis wants to use open-to-close consistency
    // https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html
    int fclose (FILE *stream) {
        if call_return == 0 {
            PROV_LOGGER.fclose(stream);
        }
    };
    int fcloseall (void) {
        if call_return == 0 {
            PROV_LOGGER.fcloseall();
        }
    };

    // https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html
    // TODO: what to do about optional third argument: mode_t mode?
    int open (const char *filename, int flags) {
        open_parser(call_return, libc::AT_FDCWD, filename, flags);
    };
    int open64 (const char *filename, int flags) {
        guard_inner_call = true;
    } {
        open_parser(call_return, libc::AT_FDCWD, filename, flags);
    };
    int creat (const char *filename, mode_t mode) {
        PROV_LOGGER.open_read(call_return, filename);
    };
    int creat64 (const char *filename, mode_t mode) {
        PROV_LOGGER.open_read(libc::AT_FDCWD, filename, call_return);
    };
    int close (int filedes) {
        if call_return == 0 {
            PROV_LOGGER.close(filedes);
        }
    };
    int close_range (unsigned int lowfd, unsigned int maxfd, int flags) {
        if call_return == 0 && flags & (libc::CLOSE_RANGE_CLOEXEC as i32) == 0 {
            PROV_LOGGER.close_range(lowfd, maxfd);
        }
    };
    void closefrom (int lowfd) {
        PROV_LOGGER.closefrom(lowfd);
    };

    // https://linux.die.net/man/2/openat
    int openat(int dirfd, const char *pathname, int flags) {
        open_parser(call_return, dirfd, pathname, flags);
    };

    // https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib-openat64.html
    int openat64(int dirfd, const char *pathname, int flags) {
        open_parser(call_return, dirfd, pathname, flags);
    };

    FILE * fdopen (int filedes, const char *opentype) {
        fopen_parser(call_return, "$unk" as *const libc::c_char, opentype);
    };

    int dup (int old) {
        PROV_LOGGER.dup_fd(old, call_return);
    };

    int dup2 (int old, int new) {
        PROV_LOGGER.dup_fd(old, new);
    };

    DIR * opendir (const char *dirname) {
        PROV_LOGGER.opendir(dirname, call_return, libc::dirfd(call_return));
    };

    DIR * fdopendir (int fd) {
        PROV_LOGGER.opendir("$unk", call_return, fd);
    };

    int closedir (DIR *dirstream) {
        if call_return == 0 {
            PROV_LOGGER.closedir(dirstream);
        }
    };

    int link (const char *oldname, const char *newname) {
        PROV_LOGGER.link(libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
    };

    int linkat (int oldfd, const char *oldname, int newfd, const char *newname, int flags) {
        PROV_LOGGER.link(oldfd, oldname, newfd, newname);
    };

    int symlink (const char *oldname, const char *newname) {
        PROV_LOGGER.symlink(libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
    };

    ssize_t readlink (const char *filename, char *buffer, size_t size) {
        PROV_LOGGER.readlink(libc::AT_FDCWD, filename);
    };
}
