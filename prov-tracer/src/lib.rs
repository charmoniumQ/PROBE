#![feature(iter_intersperse)]
mod util;
mod strace_prov_logger;
mod null_prov_logger;
mod prov_logger;
mod globals;

use strace_prov_logger::StraceProvLogger;
use prov_logger::{ProvLogger, CType, CPrimType, ArgType, CFuncSig, CFuncSigs};
use null_prov_logger::NullProvLogger;

type MyProvLogger = StraceProvLogger;

thread_local! {
    static PROV_LOGGER: std::cell::RefCell<MyProvLogger> = std::cell::RefCell::new(MyProvLogger::new(&CFUNC_SIGS));
}

fn fopen_parser(prov_logger: &mut MyProvLogger, file: *const libc::FILE, filename: *const libc::c_char, opentype: *const libc::c_char) {
    // The POSIX manual does not define libc::fileno to have any side-effects.
    // The current implementation in Glibc has no side-effects (see libio/fileno.c and libio/iolibio.h).
    // Thus it should be safe to insert a call to fileno and safe to cast *const to *mut.
    if !file.is_null() {
        let fd = unsafe { libc::fileno(file as *mut libc::FILE) };
        let opentype_pair = unsafe { (opentype.read() as u8 as char, opentype.offset(1).read() as u8 as char) };
        match opentype_pair {
            ('r', '\0') => prov_logger.open_read     (libc::AT_FDCWD, filename, fd),
            ('r', '+' ) => prov_logger.open_readwrite(libc::AT_FDCWD, filename, fd),
            ('w', '\0') => prov_logger.open_overwrite(libc::AT_FDCWD, filename, fd),
            // w+ creates or truncates a new file, so it does not need to be readwrite; just write
            // However, the fd can be read and written by different processes
            ('w', '+' ) => prov_logger.open_overwriteshared(libc::AT_FDCWD, filename, fd),
            ('a', '\0') => prov_logger.open_writepart(libc::AT_FDCWD, filename, fd),
            ('a', '+' ) => prov_logger.open_readwrite(libc::AT_FDCWD, filename, fd),
            (x, y) => panic!("Unknown opentypes {:?} {:?}", x, y),
        };
    }
}

fn open_parser(prov_logger: &mut MyProvLogger, ret: libc::c_int, dirfd: libc::c_int, filename: *const libc::c_char, flags: libc::c_int) {
    if false {
    } else if (flags & libc::O_ACCMODE) == libc::O_RDWR {
        if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            // See comment on fopen w+
            prov_logger.open_overwriteshared(dirfd, filename, ret);
        } else {
            prov_logger.open_readwrite(dirfd, filename, ret);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_RDONLY {
        if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            // Truncates the file, which is a write
            // And then reads from it. Maybe someone else wrote to it since then.
            prov_logger.open_readwrite(dirfd, filename, ret);
        } else {
            prov_logger.open_read(dirfd, filename, ret);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_WRONLY {
        if flags & libc::O_TMPFILE != 0 {
            prov_logger.open_overwrite(dirfd, std::ptr::null(), ret);
        } else if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            prov_logger.open_overwrite(dirfd, filename, ret);
        } else {
            prov_logger.open_writepart(dirfd, filename, ret);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_PATH {
        prov_logger.open_none(dirfd, filename, ret);
    }
}

extern crate project_specific_macros;
project_specific_macros::populate_libc_calls_and_hook_fns!{
    // https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html
    FILE * fopen (const char *filename, const char *opentype) {
        fopen_parser(prov_logger, call_return, filename, opentype);
    };
    FILE * fopen64 (const char *filename, const char *opentype) {
        fopen_parser(prov_logger, call_return, filename, opentype);
    };
    FILE * freopen (const char *filename, const char *opentype, FILE *stream) {
        prov_logger.close(libc::fileno(stream));
        fopen_parser(prov_logger, stream, filename, opentype);
    };
    FILE * freopen64 (const char *filename, const char *opentype, FILE *stream) {
        prov_logger.close(libc::fileno(stream));
        fopen_parser(prov_logger, stream, filename, opentype);
    };

    // We need these in case an analysis wants to use open-to-close consistency
    // https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html
    int fclose (FILE *stream) {
        if call_return == 0 {
            prov_logger.close(libc::fileno(stream));
        }
    };
    int fcloseall (void) {
        if call_return == 0 {
            prov_logger.fcloseall();
        }
    };

    // https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html
    // TODO: what to do about optional third argument: mode_t mode?
    int open (const char *filename, int flags) {
        open_parser(prov_logger, call_return, libc::AT_FDCWD, filename, flags);
    };
    int open64 (const char *filename, int flags) {
        guard_inner_call = true;
    } {
        open_parser(prov_logger, call_return, libc::AT_FDCWD, filename, flags);
    };
    int creat (const char *filename, mode_t mode) {
        prov_logger.open_read(libc::AT_FDCWD, filename, call_return);
    };
    int creat64 (const char *filename, mode_t mode) {
        prov_logger.open_read(libc::AT_FDCWD, filename, call_return);
    };
    int close (int filedes) {
        if call_return == 0 {
            prov_logger.close(filedes);
        }
    };
    int close_range (unsigned int lowfd, unsigned int maxfd, int flags) {
        if call_return == 0 && flags & (libc::CLOSE_RANGE_CLOEXEC as i32) == 0 {
            prov_logger.close_range(lowfd, maxfd);
        }
    };
    void closefrom (int lowfd) {
        prov_logger.closefrom(lowfd);
    };

    // https://linux.die.net/man/2/openat
    int openat(int dirfd, const char *pathname, int flags) {
        open_parser(prov_logger, call_return, dirfd, pathname, flags);
    };

    // https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib-openat64.html
    int openat64(int dirfd, const char *pathname, int flags) {
        open_parser(prov_logger, call_return, dirfd, pathname, flags);
    };

    FILE * fdopen (int filedes, const char *opentype) {
        fopen_parser(prov_logger, call_return, std::ptr::null(), opentype);
    };

    int dup (int old) {
        prov_logger.dup_fd(old, call_return);
    };

    int dup2 (int old, int new) {
        prov_logger.dup_fd(old, new);
    };

    DIR * opendir (const char *dirname) {
        prov_logger.opendir(dirname, call_return, libc::dirfd(call_return));
    };

    DIR * fdopendir (int fd) {
        prov_logger.opendir(std::ptr::null(), call_return, fd);
    };

    int closedir (DIR *dirstream) {
        if call_return == 0 {
            prov_logger.closedir(dirstream);
        }
    };

    int link (const char *oldname, const char *newname) {
        prov_logger.link(libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
    };

    int linkat (int oldfd, const char *oldname, int newfd, const char *newname, int flags) {
        prov_logger.link(oldfd, oldname, newfd, newname);
    };

    int symlink (const char *oldname, const char *newname) {
        prov_logger.symlink(libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
    };

    ssize_t readlink (const char *filename, char *buffer, size_t size) {
        prov_logger.readlink(libc::AT_FDCWD, filename);
    };
}
