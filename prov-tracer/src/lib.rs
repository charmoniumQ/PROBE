#![feature(iter_intersperse)]
#![feature(thread_id_value)]
#![feature(absolute_path)]
#![allow(unused_imports)]
mod util;
mod globals;

extern crate project_specific_macros;
project_specific_macros::populate_libc_calls_and_hook_fns!{
    // https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html
    FILE * fopen (const char *filename, const char *opentype) {
        self.prov_logger.pre_open(OpenMode::parse_fopen_str(opentype), libc::AT_FDCWD, filename);
    } {
        let fd = if ret.is_null() { 0 } else { unsafe {libc::fileno(ret)} };
        self.prov_logger.post_open(OpenMode::parse_fopen_str(opentype), libc::AT_FDCWD, filename, fd, this_errno);
    }
    FILE * fopen64 (const char *filename, const char *opentype) {
        self.prov_logger.pre_open(OpenMode::parse_fopen_str(opentype), libc::AT_FDCWD, filename);
    } {
        let fd = if ret.is_null() { 0 } else { unsafe {libc::fileno(ret)} };
        self.prov_logger.post_open(OpenMode::parse_fopen_str(opentype), libc::AT_FDCWD, filename, fd, this_errno);
    }
    FILE * freopen (const char *filename, const char *opentype, FILE *stream) {
        self.tmp_fd = unsafe {libc::fileno(stream)};
        self.prov_logger.pre_close(self.tmp_fd);
        self.prov_logger.pre_open(OpenMode::parse_fopen_str(opentype), libc::AT_FDCWD, filename);
    } {
        // TODO: consider the case where the close succeeds but the open fails, etc.
        let emulated_ret = if ret.is_null() { -1 } else { 0 };
        self.prov_logger.post_close(self.tmp_fd, emulated_ret, this_errno);
        let fd = if ret.is_null() { 0 } else { unsafe {libc::fileno(ret)} };
        self.prov_logger.post_open(OpenMode::parse_fopen_str(opentype), libc::AT_FDCWD, filename, fd, this_errno);
    }
    FILE * freopen64 (const char *filename, const char *opentype, FILE *stream) {
        self.tmp_fd = unsafe {libc::fileno(stream)};
        self.prov_logger.pre_close(self.tmp_fd);
        self.prov_logger.pre_open(OpenMode::parse_fopen_str(opentype), libc::AT_FDCWD, filename);
    } {
        // TODO: consider the case where the close succeeds but the open fails, etc.
        let emulated_ret = if ret.is_null() { -1 } else { 0 };
        self.prov_logger.post_close(self.tmp_fd, emulated_ret, this_errno);
        let fd = if ret.is_null() { 0 } else { unsafe {libc::fileno(ret)} };
        self.prov_logger.post_open(OpenMode::parse_fopen_str(opentype), libc::AT_FDCWD, filename, fd, this_errno);
    }

    // We need these in case an analysis wants to use open-to-close consistency
    // https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html
    int fclose (FILE *stream) guard_call {
        self.tmp_fd = unsafe {libc::fileno(stream)};
        self.prov_logger.pre_close(self.tmp_fd);
    } {
        self.prov_logger.post_close(self.tmp_fd, ret, this_errno);
    }
    int fcloseall(void) {
        panic!("Unimplemented");
    } {
        panic!("Unimplemented");
    }

    // https://linux.die.net/man/2/openat
    int openat(int dirfd, const char *pathname, int flags) {
        self.prov_logger.pre_open(OpenMode::parse_open_bits(flags), dirfd, pathname);
    } {
        self.prov_logger.post_open(OpenMode::parse_open_bits(flags), dirfd, pathname, ret, this_errno);
    }

    // https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib-openat64.html
    int openat64(int dirfd, const char *pathname, int flags) {
        self.prov_logger.pre_open(OpenMode::parse_open_bits(flags), libc::AT_FDCWD, pathname);
    } {
        self.prov_logger.post_open(OpenMode::parse_open_bits(flags), libc::AT_FDCWD, pathname, ret, this_errno);
    }

    // https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html
    // TODO: what to do about optional third argument: mode_t mode?
    int open (const char *filename, int flags) guard_call {
        self.prov_logger.pre_open(OpenMode::parse_open_bits(flags), libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_open(OpenMode::parse_open_bits(flags), libc::AT_FDCWD, filename, ret, this_errno);
    }
    int open64 (const char *filename, int flags) guard_call {
        self.prov_logger.pre_open(OpenMode::parse_open_bits(flags), libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_open(OpenMode::parse_open_bits(flags), libc::AT_FDCWD, filename, ret, this_errno);
    }
    int creat (const char *filename, mode_t mode) {
        self.prov_logger.pre_open(OpenMode::WritePart, libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_open(OpenMode::WritePart, libc::AT_FDCWD, filename, ret, this_errno);
    }
    int creat64 (const char *filename, mode_t mode) {
        self.prov_logger.pre_open(OpenMode::WritePart, libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_open(OpenMode::WritePart, libc::AT_FDCWD, filename, ret, this_errno);
    }
    int close (int filedes) guard_call {
        self.prov_logger.pre_close(filedes);
    } {
        self.prov_logger.post_close(filedes, ret, this_errno);
    }
    int close_range (unsigned int lowfd, unsigned int maxfd, int flags) {
        panic!("Unimplemented");
    } {
        panic!("Unimplemented");
    }
    void closefrom (int lowfd) {
        panic!("Unimplemented");
    } {
        panic!("Unimplemented");
    }

    // https://www.gnu.org/software/libc/manual/html_node/Duplicating-Descriptors.html
    int dup (int old) {
        self.prov_logger.pre_dup(old, 0);
    } {
        self.prov_logger.post_dup(old, ret, ret, this_errno);
    }

    int dup2 (int old, int new) {
        self.prov_logger.pre_dup(old, new);
        self.prov_logger.pre_close(new);
    } {
        self.prov_logger.post_close(new, ret, this_errno);
        self.prov_logger.post_dup(old, new, ret, this_errno);
    }

    // https://www.man7.org/linux/man-pages/man2/dup.2.html
    int dup3 (int old, int new) {
        self.prov_logger.pre_dup(old, new);
        self.prov_logger.pre_close(new);
    } {
        self.prov_logger.post_close(new, ret, this_errno);
        self.prov_logger.post_dup(new, old, ret, this_errno);
    }

    // https://www.gnu.org/software/libc/manual/html_node/Control-Operations.html#index-fcntl-function
    //int fcntl (int filedes, int command, …)
    // TODO

    // https://www.gnu.org/software/libc/manual/html_node/Working-Directory.html
    int chdir (const char *filename) {
        self.prov_logger.pre_op(UnaryFileOp::Chdir, libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_op(UnaryFileOp::Chdir, libc::AT_FDCWD, filename, ret, this_errno);
    }

    int fchdir (int filedes) {
        self.prov_logger.pre_op(UnaryFileOp::Chdir, filedes, "".as_ptr() as *const i8);
    } {
        self.prov_logger.post_op(UnaryFileOp::Chdir, filedes, "".as_ptr() as *const i8, ret, this_errno);
    }

    // https://www.gnu.org/software/libc/manual/html_node/Opening-a-Directory.html
    DIR * opendir (const char *dirname) {
        self.prov_logger.pre_op(UnaryFileOp::Opendir, libc::AT_FDCWD, dirname);
    } {
        let fd = unsafe { libc::dirfd(dirname as *mut libc::DIR) };
        self.prov_logger.post_op(UnaryFileOp::Opendir, libc::AT_FDCWD, dirname, fd, this_errno);
    }

    DIR * fdopendir (int fd) {
        self.prov_logger.pre_op(UnaryFileOp::Opendir, fd, "".as_ptr() as *const i8);
    } {
        let emulated_ret = if ret.is_null() { -1 } else { 0 };
        self.prov_logger.post_op(UnaryFileOp::Opendir, fd, "".as_ptr() as *const i8, emulated_ret, this_errno);
    }

    // TODO:
    // readdir readdir_r readdir64 readdir64_r
    // rewindir, seekdir, telldir
    // scandir, scandirat

    // // https://www.gnu.org/software/libc/manual/html_node/Working-with-Directory-Trees.html
    int ftw (const char *filename, __ftw_func_t func, int descriptors) {
        self.prov_logger.pre_op(UnaryFileOp::Walk, libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_op(UnaryFileOp::Walk, libc::AT_FDCWD, filename, ret, this_errno);
    }

    int ftw64 (const char *filename, __ftw64_func_t func, int descriptors)  {
        self.prov_logger.pre_op(UnaryFileOp::Walk, libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_op(UnaryFileOp::Walk, libc::AT_FDCWD, filename, ret, this_errno);
    }

    int nftw (const char *filename, __nftw_func_t func, int descriptors, int flag)  {
        self.prov_logger.pre_op(UnaryFileOp::Walk, libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_op(UnaryFileOp::Walk, libc::AT_FDCWD, filename, ret, this_errno);
    }

    int nftw64 (const char *filename, __nftw64_func_t func, int descriptors, int flag)  {
        self.prov_logger.pre_op(UnaryFileOp::Walk, libc::AT_FDCWD, filename);
    } {
        self.prov_logger.post_op(UnaryFileOp::Walk, libc::AT_FDCWD, filename, ret, this_errno);
    }

    // https://www.gnu.org/software/libc/manual/html_node/Hard-Links.html
    int link (const char *oldname, const char *newname) {
        self.prov_logger.pre_op2(BinaryFileOp::Hardlink, libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
    } {
        self.prov_logger.post_op2(BinaryFileOp::Hardlink, libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname, ret, this_errno);
    }

    int linkat (int oldfd, const char *oldname, int newfd, const char *newname, int flags) {
        self.prov_logger.pre_op2(BinaryFileOp::Hardlink, oldfd, oldname, newfd, newname);
    } {
        self.prov_logger.post_op2(BinaryFileOp::Hardlink, oldfd, oldname, newfd, newname, ret, this_errno);
    }

    // https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html
    int symlink (const char *oldname, const char *newname) {
        self.prov_logger.pre_op2(BinaryFileOp::Symlink, libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
    } {
        self.prov_logger.post_op2(BinaryFileOp::Symlink, libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname, ret, this_errno);
    }

    // // https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html
    int symlinkat(const char *target, int newdirfd, const char *linkpath) {
        self.prov_logger.pre_op2(BinaryFileOp::Symlink, libc::AT_FDCWD, target, newdirfd, linkpath);
    } {
        self.prov_logger.post_op2(BinaryFileOp::Symlink, libc::AT_FDCWD, target, newdirfd, linkpath, ret, this_errno);
    }

    ssize_t readlink (const char *filename, char *buffer, size_t size) {
        self.prov_logger.pre_op(UnaryFileOp::Readlink, libc::AT_FDCWD, filename);
    } {
        let emulated_ret = if ret > 0 { 0 } else { -1 };
        self.prov_logger.post_op(UnaryFileOp::Readlink, libc::AT_FDCWD, filename, emulated_ret, this_errno);
    }

    ssize_t readlinkat (int dirfd, const char *filename, char *buffer, size_t size) {
        self.prov_logger.pre_op(UnaryFileOp::MetadataRead, dirfd, filename);
    } {
        let emulated_ret = if ret > 0 { 0 } else { -1 };
        self.prov_logger.post_op(UnaryFileOp::MetadataRead, dirfd, filename, emulated_ret, this_errno);
    }

    int execv (const char *filename, char **const argv) { } { }

    int execl (const char *filename, const char * arg0/*, ...*/) { } { }

    int execve (const char *filename, char **const argv, char **const envp) { } { }

    int fexecve (int fd, char **const filename, char **const argv, char **const envp) { } { }

    int execle (const char *filename, const char * arg0/*, ..., char **const envp*/) { } { }

    int execvp (const char *filename, char **const argv, char **const envp) { } { }

    int execlp (const char *filename, char **const argv/*, ...*/) { } { }

    // https://linux.die.net/man/3/execvpe1
    int execvpe(const char *file, char **const argv, char **const envp) { } { }

    pid_t fork (void) { } { }
    pid_t _Fork (void) { } { }
    pid_t vfork (void) { } { }
}

#[derive(Debug)]
enum OpenMode {
    Read, ReadWrite, Overwrite, WritePart
}

impl OpenMode {
    fn parse_fopen_str(opentype: *const libc::c_char) -> OpenMode {
        let first_char  = unsafe { (opentype.offset(0).read()) as u8 as char };
        let second_char = unsafe { (opentype.offset(1).read()) as u8 as char };
        let third_char = if second_char != '\0' {
            unsafe { (opentype.offset(2).read()) as u8 as char}
        } else { '\0' };
        let append = second_char == '+' || third_char == '+';
        match (first_char, append) {
            ('r', false) => OpenMode::Read,
            ('r', true ) => OpenMode::ReadWrite,
            ('w', false) => OpenMode::Overwrite,
            ('w', true ) => OpenMode::Overwrite,
            ('a', false) => OpenMode::WritePart,
            ('a', true ) => OpenMode::ReadWrite,
            (x, _) => panic!("Unknown opentypes {:?}", x),
        }
    }

    fn parse_open_bits(flags: libc::c_int) -> OpenMode {
        if (flags & libc::O_ACCMODE) == libc::O_RDWR {
            if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
                OpenMode::Overwrite
            } else {
                OpenMode::ReadWrite
            }
        } else if (flags & libc::O_ACCMODE) == libc::O_RDONLY {
            if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
                // Truncates the file, which is a write
                // And then reads from it. Maybe someone else wrote to it since then.
                OpenMode::ReadWrite
            } else {
                OpenMode::Read
            }
        } else if (flags & libc::O_ACCMODE) == libc::O_WRONLY {
            if flags & libc::O_TMPFILE != 0 {
                OpenMode::Overwrite
            } else if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
                OpenMode::Overwrite
            } else {
                OpenMode::WritePart
            }
        } else if (flags & libc::O_ACCMODE) == libc::O_PATH {
            // TODO: Note that opening with O_PATH can cause a file metadata read
            // int fd = open(path, O_PATH | O_DIRECTORY);
            // struct stat buf;
            // fstatat(fd, &buf);

            // TODO: Note that opening with O_PATH on a directory can cause a directory list
            // int fd = open(path, O_PATH | O_DIRECTORY);
            // DIR* dir = dirfd(fd);
            // readdir(dir);

            panic!("I don't really know what to do with this O_PATH")
        } else {
            panic!("I don't really know what to do with this open mode")
        }
    }
}

// https://unix.stackexchange.com/questions/248408/file-descriptors-across-exec
// TODO: Note that file descriptors can be shared across execs.

#[derive(Debug)]
enum UnaryFileOp {
    Chdir, Opendir, Walk, MetadataRead, MetadataWritePart, Readlink
}

#[derive(Debug)]
enum BinaryFileOp {
    Hardlink, Symlink, Move
}

use std::path::PathBuf;

trait ProvLogger {
    #[allow(unused_variables)]
    fn pre_open(
        &mut self, mode: OpenMode,
        dirfd: libc::c_int, path: *const libc::c_char,
    ) { }
    #[allow(unused_variables)]
    fn pre_close(&mut self, fd: libc::c_int) { }
    #[allow(unused_variables)]
    fn pre_dup(&mut self, old: libc::c_int, new: libc::c_int) { }
    #[allow(unused_variables)]
    fn pre_op(
        &mut self, op_code: UnaryFileOp,
        dirfd: libc::c_int, path: *const libc::c_char,
    ) { }
    #[allow(unused_variables)]
    fn pre_op2(
        &mut self, op_code: BinaryFileOp,
        dirfd0: libc::c_int, path0: *const libc::c_char,
        dirfd1: libc::c_int, path1: *const libc::c_char,
    ) { }
    #[allow(unused_variables)]
    fn post_open(
        &mut self, mode: OpenMode, dirfd: libc::c_int, path: *const libc::c_char,
        fd: libc::c_int, this_errno: errno::Errno,
    ) { }
    #[allow(unused_variables)]
    fn post_close(
        &mut self, fd: libc::c_int,
        ret: libc::c_int, this_errno: errno::Errno,
    ) { }
    #[allow(unused_variables)]
    fn post_dup(
        &mut self, old: libc::c_int, new: libc::c_int,
        ret: libc::c_int, this_errno: errno::Errno,
    ) { }
    #[allow(unused_variables)]
    fn post_op(
        &mut self, op_code: UnaryFileOp, dirfd: libc::c_int, path: *const libc::c_char,
        ret: libc::c_int, this_errno: errno::Errno,
    ) { }
    #[allow(unused_variables)]
    fn post_op2(
        &mut self, op_code: BinaryFileOp,
        dirfd0: libc::c_int, path0: *const libc::c_char,
        dirfd1: libc::c_int, path1: *const libc::c_char,
        ret: libc::c_int, this_errno: errno::Errno,
    ) { }
}

struct NullCallLogger();
impl NullCallLogger { fn new() -> Self { Self() } }
impl CallLogger for NullCallLogger { }

struct VerboseCallLogger {
    file: std::boxed::Box<std::fs::File>,
}
impl VerboseCallLogger {
    fn get_file() -> std::fs::File {
        crate::globals::ENABLE_TRACE.set(false);
        let filename = std::env::var("PROV_TRACER_FILE")
            .unwrap_or("prov_trace.%p.%t.%c".to_string())
            .replace("%p", std::process::id().to_string().as_str())
            .replace("%t", std::thread::current().id().as_u64().to_string().as_str())
            .replace("%c", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_millis().to_string().as_str())
            // .replace("%r", .as_str())
            ;
        let file = std::fs::File::create(filename).unwrap();
        crate::globals::ENABLE_TRACE.set(true);
        file
    }
    fn new() -> Self {
        println!("(VerboseCallLogger::new");
        let file = std::boxed::Box::new(Self::get_file());
        println!(")");
        Self { file }
    }
}

struct CallLoggerToProvLogger<MyProvLogger> {
    prov_logger: MyProvLogger,
    tmp_fd: libc::c_int,
}

impl<MyProvLogger: ProvLogger> CallLoggerToProvLogger<MyProvLogger> {
    fn new(prov_logger: MyProvLogger) -> Self {
        Self {
            prov_logger,
            tmp_fd: 0,
        }
    }
}

use std::io::Write;
struct VerboseProvLogger {
    file: std::fs::File,
}
impl VerboseProvLogger {
    fn new() -> Self {
        println!("(VerboseProvLogger::new");
        crate::globals::ENABLE_TRACE.set(false);
        let filename =
            std::env::var("PROV_TRACER_FILE")
            .unwrap_or("prov_trace.%p.%t.%c".to_string())
            .replace("%p", std::process::id().to_string().as_str())
            .replace("%t", std::thread::current().id().as_u64().to_string().as_str())
            .replace("%c", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_millis().to_string().as_str())
            ;
        let file = std::fs::File::create(filename).unwrap();
        crate::globals::ENABLE_TRACE.set(true);
        println!(")");
        Self { file }
    }
}
impl ProvLogger for VerboseProvLogger {
    fn post_open(
        &mut self, mode: OpenMode,
        dirfd: libc::c_int, path: *const libc::c_char,
        fd: libc::c_int, this_errno: errno::Errno,
    ) {
        if fd == -1 {
            writeln!(self.file, "open mode: {:?} file: ({:?} {:?}) err: {:?}", mode, dirfd, util::short_cstr(path), this_errno).unwrap();
        } else {
            writeln!(self.file, "open mode: {:?} file: ({:?} {:?}) fd: {:?}", mode, dirfd, util::short_cstr(path), fd).unwrap();
        }
    }
    fn post_close(
        &mut self,
        fd: libc::c_int,
        ret: libc::c_int, this_errno: errno::Errno,
    ) {
        if ret == -1 {
            writeln!(self.file, "close fd: {:?} err: {:?}", fd, this_errno).unwrap();
        } else {
            writeln!(self.file, "close fd: {:?}", fd).unwrap();
        }
    }
    fn post_dup(
        &mut self,
        old: libc::c_int, new: libc::c_int,
        ret: libc::c_int, this_errno: errno::Errno
    ) {
        if ret == -1 {
            writeln!(self.file, "dup fd0: {:?} fd1: {:?} err: {:?}", old, new, this_errno).unwrap();
        } else {
            writeln!(self.file, "dup fd0: {:?} fd1: {:?}", old, new).unwrap();
        }
    }
    fn post_op(
        &mut self, op_code: UnaryFileOp,
        dirfd: libc::c_int, path: *const libc::c_char,
        ret: libc::c_int, this_errno: errno::Errno,
    ) {
        if ret == -1 {
            writeln!(self.file, "op code: {:?} file: ({:?} {:?}) err: {:?}", op_code, dirfd, util::short_cstr(path), this_errno).unwrap();
        } else {
            writeln!(self.file, "op code: {:?} file: ({:?} {:?})", op_code, dirfd, util::short_cstr(path)).unwrap();
        }
    }
    fn post_op2(
        &mut self,
        op_code: BinaryFileOp,
        dirfd0: libc::c_int, path0: *const libc::c_char,
        dirfd1: libc::c_int, path1: *const libc::c_char,
        ret: libc::c_int, this_errno: errno::Errno,
    ) {
        if ret == -1 {
            writeln!(self.file, "op code: {:?} file0: ({:?} {:?}) file1: ({:?} {:?}) err: {:?}", op_code, dirfd0, util::short_cstr(path0), dirfd1, util::short_cstr(path1), this_errno).unwrap();
        } else {
            writeln!(self.file, "op code: {:?} file0: ({:?} {:?}) file1: ({:?} {:?})", op_code, dirfd0, util::short_cstr(path0), dirfd1, util::short_cstr(path1)).unwrap();
        }
    }
}

redhook::hook! {
    #![feature(c_variadic)]
    unsafe fn execlp(file: *const libc::c_char, mut args: ...) -> i32 => my_execlp {
        println!("execlp");
        redhook::real!(execlp)(file, args);
    }
}

// pub struct SemanticCallLogger {
//     log_file: std::fs::File,
//     chroot_dir: PathBuf,
//     cwd: PathBuf,
//     tmp_dirfd: libc::c_int,
//     tmp_filename: *const libc::c_char,
//     tmp_path: PathBuf,
//     file_descriptors: std::collections::HashMap::<i32, PathBuf>,
//     read_contents_and_metadata: std::collections::HashSet::<PathBuf>,
//     read_metadata: std::collections::HashSet::<PathBuf>,
//     copied_contents_and_metadata: std::collections::HashSet::<PathBuf>,
//     copied_metadata: std::collections::HashSet::<PathBuf>,
//     // TODO: handle symlinks and hardlinks
// }

// // impl Drop for SemanticCallLogger {
// //     fn drop(&mut self) {
// //         self.read_contents_and_metadata.map(|read_contents| println!(""))
// //     }
// // }

// impl SemanticCallLogger {
//     fn new() -> Self {
//         globals::ENABLE_TRACE.set(false);
//         let filename =
//             std::env::var("PROV_TRACER_FILE")
//             .unwrap_or("%p.%t.prov_trace".to_string())
//             .replace("%p", std::process::id().to_string().as_str())
//             .replace("%t", std::thread::current().id().as_u64().to_string().as_str());
//         let log_file = std::fs::File::create(filename).unwrap();
//         let dirname = std::env::var("PROV_TRACER_DIR")
//             .unwrap_or("%p.prov_files".to_string());
//         globals::ENABLE_TRACE.set(true);
//         Self {
//             log_file,
//             chroot_dir: PathBuf::from(dirname),
//             cwd: std::env::current_dir().unwrap(),
//             tmp_drfd: libc::c_int,
//             tmp_filename: *const libc::c_char,
//             tmp_path: PathBuf,
//             file_descriptors: std::collections::HashMap::new(),
//             read_contents_and_metadata: std::collections::HashSet::new(),
//             read_metadata: std::collections::HashSet::new(),
//             copied_contents_and_metadata: std::collections::HashSet::new(),
//             copied_metadata: std::collections::HashSet::new(),
//         }
//     }

//     fn normalize_path(&self, path: *const libc::c_char) -> PathBuf {
//         use std::os::unix::ffi::OsStrExt;
//         let mut ret = self.cwd.clone();
//         ret.push(std::ffi::OsStr::from_bytes(unsafe { std::ffi::CStr::from_ptr(path) }.to_bytes()));
//         ret.canonicalize().unwrap()
//         // TODO: decide what kind of canonicalizing we should be doing
//     }

//     fn normalize_pathat(&self, dirfd: libc::c_int, path: *const libc::c_char) -> PathBuf {
//         use std::os::unix::ffi::OsStrExt;
//         let subpath = PathBuf::from(std::ffi::OsStr::from_bytes(unsafe { std::ffi::CStr::from_ptr(path) }.to_bytes()));
//         let base = if dirfd == libc::AT_FDCWD {
//             assert!(self.cwd == std::env::current_dir().unwrap());
//             &self.cwd
//         } else {
//             panic!("");
//             // self.get_dirfd(&dirfd).expect(UNKNOWN_FD_MSG)
//         };
//         std::path::Path::join(base, subpath)
//         // wTODO: decide what kind of canonicalizing we should be doing
//     }

//     fn metadata_read(&mut self, dirfd: libc::c_int, name: *const libc::c_char) {
//         let path = self.normalize_pathat(dirfd, name);
//         println!("metadata_read {:?}", path);
//         if !self.copied_metadata.contains(&path) && !self.copied_contents_and_metadata.contains(&path) {
//             self.read_metadata.insert(path);
//         }
//     }

//     fn metadata_writepart(&mut self, dirfd: libc::c_int, name: *const libc::c_char) {
//         let path = self.normalize_pathat(dirfd, name);
//         println!("metadata_writepart {:?}", path);
//         // note that reading contents implies reading metadta
//         if self.read_metadata.contains(&path) || self.read_contents_and_metadata.contains(&path) {
//             write!(self.file, "copy-metadata-if-exists {:?}", path).unwrap();
//             println!("copy-metadata-if-exists {:?}", path);
//             self.read_metadata.remove(&path);
//             self.copied_metadata.insert(path);
//         }
//     }

//     fn open_read(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
//         let path = self.normalize_pathat(dirfd, filename);
//         println!("open_read {:?}", path);
//         if !self.copied_contents_and_metadata.contains(&path) {
//             self.copied_contents_and_metadata.insert(path);
//         }
//     }

//     fn open_writepart(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
//         let path = self.normalize_pathat(dirfd, filename);
//         println!("open_writepart {:?}", path);
//         if self.read_contents_and_metadata.contains(&path) {
//             write!(self.file, "copy-if-exists {:?}", path).unwrap();
//             println!("copy-if-exists {:?}", path);
//             self.read_contents_and_metadata.remove(&path);
//             self.copied_contents_and_metadata.insert(path);
//         } else {
//             // Writing part of a file is semantically, read all of file into buffer, modify buffer, and write all of buffer into file.
//             // Therefore, we consider this a read-contents operation
//             self.read_contents_and_metadata.insert(path);
//         }
//     }

//     fn open_readwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
//         self.open_writepart(dirfd, filename);
//     }

//     fn open_overwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
//         let path = self.normalize_pathat(dirfd, filename);
//         println!("open_overwrite {:?}", path);
//         if self.read_contents_and_metadata.contains(&path) {
//             write!(self.file, "copy-if-exists {:?}", path).unwrap();
//             println!("copy-if-exists {:?}", path);
//             self.read_contents_and_metadata.remove(&path);
//             self.copied_contents_and_metadata.insert(path);
//         } else {
//             // It is as if we copied, since this gets generated by the program
//             self.copied_contents_and_metadata.insert(path);
//         }
//     }

//     fn close(&mut self, fd: libc::c_int) {
//         println!("close {:?}", fd);
//         self.file_descriptors.remove(&fd);
//     }

//     fn fcloseall(&mut self) {
//         println!("fcloseall");
//         self.file_descriptors.clear();
//     }

//     fn close_range(&mut self, lowfd: libc::c_uint, maxfd: libc::c_uint) {
//         println!("close_range {} {}", lowfd, maxfd);
//         self.file_descriptors.retain(|&fd, _| !((lowfd as i32) <= fd && fd <= (maxfd as i32)));
//     }

//     fn closefrom(&mut self, lowfd: libc::c_int) {
//         println!("closefrom {}", lowfd);
//         self.file_descriptors.retain(|&fd, _| fd < lowfd);
//     }

//     fn dup_fd(&mut self, _oldfd: libc::c_int, _newfd: libc::c_int) {
//         panic!("TODO: we don't support dup_fd yet");
//     }

//     fn chdir(&mut self, filename: *const libc::c_char) {
//         self.cwd = self.normalize_path(filename);
//     }

//     fn fchdir(&mut self, filedes: libc::c_int) {
//         self.cwd = self.file_descriptors.get(&filedes).expect(UNKNOWN_FD_MSG).to_path_buf();
//     }
//     fn ftw(&mut self, filename: *const libc::c_char) { }
//     fn opendir(&mut self, fd: libc::c_int) { }
//     fn link(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char, newfd: libc::c_int, newname: *const libc::c_char) { }
//     fn symlink(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char, newfd: libc::c_int, newname: *const libc::c_char) { }
//     fn readlink(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char) { }
// }

const UNKNOWN_FD_MSG: &str = "Original program would probably have crashed here, because it accesses a dirfd it never opened";

struct DisableLoggingInDrop<T> { inner: T }
impl<T> DisableLoggingInDrop<T> {
    fn new(inner: T) -> Self { Self { inner } }
}
impl<T> Drop for DisableLoggingInDrop<T> {
    fn drop(&mut self) {
        crate::globals::ENABLE_TRACE.set(false);
    }
}

thread_local! {
    static CALL_LOGGER: std::cell::RefCell<DisableLoggingInDrop<
        VerboseCallLogger
        // CallLoggerToProvLogger<VerboseProvLogger>
     >> = std::cell::RefCell::new(DisableLoggingInDrop::new(
         VerboseCallLogger::new()
        // CallLoggerToProvLogger::new(VerboseProvLogger::new())
    ));
}
