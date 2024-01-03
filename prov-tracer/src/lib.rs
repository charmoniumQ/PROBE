#![feature(iter_intersperse)]
#![feature(absolute_path)]
#![allow(unused_imports)]
mod util;
mod strace_prov_logger;
mod null_prov_logger;
mod semantic_prov_logger;
mod prov_logger;
mod globals;

use strace_prov_logger::StraceProvLogger;
use null_prov_logger::NullProvLogger;
use semantic_prov_logger::SemanticProvLogger;
use prov_logger::{ProvLogger, CType, CPrimType, ArgType, CFuncSig, CFuncSigs};

type MyProvLogger = SemanticProvLogger;

thread_local! {
    static PROV_LOGGER: std::cell::RefCell<std::mem::ManuallyDrop<MyProvLogger>> = std::cell::RefCell::new(std::mem::ManuallyDrop::new(MyProvLogger::new(&CFUNC_SIGS)));
}

fn fopen_parser(prov_logger: &mut MyProvLogger, filename: *const libc::c_char, opentype: *const libc::c_char) {
    // The POSIX manual does not define libc::fileno to have any side-effects.
    // The current implementation in Glibc has no side-effects (see libio/fileno.c and libio/iolibio.h).
    // Thus it should be safe to insert a call to fileno and safe to cast *const to *mut.
    let first_char  = unsafe { (opentype.offset(0).read()) as u8 as char };
    let second_char = unsafe { (opentype.offset(1).read()) as u8 as char };
    let third_char = if second_char != '\0' {
        unsafe { (opentype.offset(2).read()) as u8 as char}
    } else { '\0' };
    let append = second_char == '+' || third_char == '+';
    match (first_char, append) {
        ('r', false) => prov_logger.open_read(libc::AT_FDCWD, filename),
        ('r', true ) => prov_logger.open_readwrite(libc::AT_FDCWD, filename),
        ('w', false) => prov_logger.open_overwrite(libc::AT_FDCWD, filename),
        ('w', true ) => prov_logger.open_overwrite(libc::AT_FDCWD, filename),
        ('a', false) => prov_logger.open_writepart(libc::AT_FDCWD, filename),
        ('a', true ) => prov_logger.open_readwrite(libc::AT_FDCWD, filename),
        (x, _) => panic!("Unknown opentypes {:?}", x),
    };
}

fn open_parser(prov_logger: &mut MyProvLogger, dirfd: libc::c_int, filename: *const libc::c_char, flags: libc::c_int) {
    if false {
    } else if (flags & libc::O_ACCMODE) == libc::O_RDWR {
        if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            prov_logger.open_overwrite(dirfd, filename);
        } else {
            prov_logger.open_readwrite(dirfd, filename);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_RDONLY {
        if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            // Truncates the file, which is a write
            // And then reads from it. Maybe someone else wrote to it since then.
            prov_logger.open_readwrite(dirfd, filename);
        } else {
            prov_logger.open_read(dirfd, filename);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_WRONLY {
        if flags & libc::O_TMPFILE != 0 {
            prov_logger.open_overwrite(dirfd, std::ptr::null());
        } else if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
            prov_logger.open_overwrite(dirfd, filename);
        } else {
            prov_logger.open_writepart(dirfd, filename);
        }
    } else if (flags & libc::O_ACCMODE) == libc::O_PATH {
        prov_logger.metadata_read(dirfd, filename);
    }
}

extern crate project_specific_macros;
project_specific_macros::populate_libc_calls_and_hook_fns!{
    // https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html
    FILE * fopen (const char *filename, const char *opentype) {
        fopen_parser(prov_logger, filename, opentype);
    } {
        if !call_return.is_null() {
            prov_logger.associate(libc::fileno(call_return), libc::AT_FDCWD, filename);
        }
        // We prepared for the effects of this call if it succeeds
        // If it fails, that is still valid, just overly conservative/unnecessary
        // Therefore, we don't need to "undo" any prov trace operation here.
    };
    FILE * fopen64 (const char *filename, const char *opentype) {
        fopen_parser(prov_logger, filename, opentype);
    } {
        if !call_return.is_null() {
            prov_logger.associate(libc::fileno(call_return), libc::AT_FDCWD, filename);
        }
    };
    FILE * freopen (const char *filename, const char *opentype, FILE *stream) {
        fopen_parser(prov_logger, filename, opentype);
        prov_logger.close(libc::fileno(stream));
    } {
        if !call_return.is_null() {
            prov_logger.associate(libc::fileno(call_return), libc::AT_FDCWD, filename);
        }
    };
    FILE * freopen64 (const char *filename, const char *opentype, FILE *stream) {
        fopen_parser(prov_logger, filename, opentype);
        prov_logger.close(libc::fileno(stream));
    } {
        if !call_return.is_null() {
            prov_logger.associate(libc::fileno(call_return), libc::AT_FDCWD, filename);
        }
    };

    // We need these in case an analysis wants to use open-to-close consistency
    // https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html
    int fclose (FILE *stream) guard_call { } {
        if call_return == 0 {
            prov_logger.close(libc::fileno(stream));
        }
    };
    int fcloseall (void) { } {
        if call_return == 0 {
            prov_logger.fcloseall();
        }
    };

    // https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html
    // TODO: what to do about optional third argument: mode_t mode?
    int open (const char *filename, int flags) guard_call {
        open_parser(prov_logger, libc::AT_FDCWD, filename, flags);
    } {
        if call_return != -1 {
            prov_logger.associate(call_return, libc::AT_FDCWD, filename);
        }
    };
    int open64 (const char *filename, int flags) guard_call {
        open_parser(prov_logger, libc::AT_FDCWD, filename, flags);
    } {
        if call_return != -1 {
            prov_logger.associate(call_return, libc::AT_FDCWD, filename);
        }
    };
    int creat (const char *filename, mode_t mode) {
        prov_logger.open_read(libc::AT_FDCWD, filename);
    } {
        if call_return != -1 {
            prov_logger.associate(call_return, libc::AT_FDCWD, filename);
        }
    };
    int creat64 (const char *filename, mode_t mode) {
        prov_logger.open_read(libc::AT_FDCWD, filename);
    } {
        if call_return != -1 {
            prov_logger.associate(call_return, libc::AT_FDCWD, filename);
        }
    };
    int close (int filedes) guard_call { } {
        if call_return == 0 {
            prov_logger.close(filedes);
        }
    };
    int close_range (unsigned int lowfd, unsigned int maxfd, int flags) { } {
        if call_return == 0 && flags & (libc::CLOSE_RANGE_CLOEXEC as i32) == 0 {
            prov_logger.close_range(lowfd, maxfd);
        }
    };
    void closefrom (int lowfd) { } {
        prov_logger.closefrom(lowfd);
    };

    // https://linux.die.net/man/2/openat
    int openat(int dirfd, const char *pathname, int flags) {
        open_parser(prov_logger, dirfd, pathname, flags);
    } {
        if call_return != -1 {
            prov_logger.associate(call_return, dirfd, pathname);
        }
    };

    // https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib-openat64.html
    int openat64(int dirfd, const char *pathname, int flags) {
        open_parser(prov_logger, dirfd, pathname, flags);
    } {
        if call_return != -1 {
            prov_logger.associate(call_return, dirfd, pathname);
        }
    };

    // https://www.gnu.org/software/libc/manual/html_node/Duplicating-Descriptors.html
    int dup (int old) { } {
        if call_return != -1 {
            prov_logger.dup_fd(old, call_return);
        }
    };

    int dup2 (int old, int new) { } {
        if call_return != -1 {
            prov_logger.close(new);
            prov_logger.dup_fd(old, new);
        }
    };

    // https://www.man7.org/linux/man-pages/man2/dup.2.html
    int dup3 (int old, int new) { } {
        if call_return != -1 {
            prov_logger.close(new);
            prov_logger.dup_fd(old, new);
        }
    };

    // https://www.gnu.org/software/libc/manual/html_node/Control-Operations.html#index-fcntl-function
    //int fcntl (int filedes, int command, …)
    // TODO

    // https://www.gnu.org/software/libc/manual/html_node/Working-Directory.html
    int chdir (const char *filename) { } {
        if call_return != -1 {
            prov_logger.chdir(filename);
        }
    };

    int fchdir (int filedes) { } {
        if call_return != -1 {
            prov_logger.fchdir(filedes);
        }
    };

    // https://www.gnu.org/software/libc/manual/html_node/Opening-a-Directory.html
    DIR * opendir (const char *dirname) { } {
        if !call_return.is_null() {
            let fd = libc::dirfd(call_return);
            prov_logger.associate(fd, libc::AT_FDCWD, dirname);
            prov_logger.opendir(fd);
        }
    };

    DIR * fdopendir (int fd) { } {
        if !call_return.is_null() {
            prov_logger.opendir(fd);
        }
    };

    // https://www.gnu.org/software/libc/manual/html_node/Working-with-Directory-Trees.html
    int ftw (const char *filename, __ftw_func_t func, int descriptors) {
        prov_logger.ftw(filename);
    } { };

    int ftw64 (const char *filename, __ftw64_func_t func, int descriptors) {
        prov_logger.ftw(filename);
    } { };

    int nftw (const char *filename, __nftw_func_t func, int descriptors, int flag) {
        prov_logger.ftw(filename);
    } { };

    int nftw64 (const char *filename, __nftw64_func_t func, int descriptors, int flag) {
        prov_logger.ftw(filename);
    } { };

    // https://www.gnu.org/software/libc/manual/html_node/Hard-Links.html
    int link (const char *oldname, const char *newname) {
        prov_logger.metadata_read(libc::AT_FDCWD, oldname);
        prov_logger.metadata_read(libc::AT_FDCWD, newname);
    } {
        if call_return == 0 {
            prov_logger.link(libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
        }
    };

    int linkat (int oldfd, const char *oldname, int newfd, const char *newname, int flags) {
        prov_logger.metadata_read(oldfd, oldname);
        prov_logger.metadata_read(newfd, newname);
    } {
        if call_return == 0 {
            prov_logger.link(oldfd, oldname, newfd, newname);
        }
    };

    // https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html
    int symlink (const char *oldname, const char *newname) {
        prov_logger.metadata_read(libc::AT_FDCWD, oldname);
        prov_logger.metadata_read(libc::AT_FDCWD, newname);
    } {
        if call_return == 0 {
            prov_logger.symlink(libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
        }
    };

    ssize_t readlink (const char *filename, char *buffer, size_t size) { } {
        if call_return == 0 {
            prov_logger.readlink(libc::AT_FDCWD, filename);
        }
    };
}
