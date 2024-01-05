#![feature(iter_intersperse)]
#![feature(thread_id_value)]
#![feature(absolute_path)]
#![allow(unused_imports)]
mod util;
mod globals;

extern crate project_specific_macros;
project_specific_macros::populate_libc_calls_and_hook_fns!{
    // https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html
    FILE * fopen (const char *filename, const char *opentype)
    {
        fopen_parser(self, filename, opentype);
    } {
        if !ret.is_null() {
            self.associate(unsafe {libc::fileno(ret)}, libc::AT_FDCWD, filename);
        }
        // We prepared for the effects of this call if it succeeds
        // If it fails, that is still valid, just overly conservative/unnecessary
        // Therefore, we don't need to "undo" any prov trace operation here.
    }
    FILE * fopen64 (const char *filename, const char *opentype) {
        fopen_parser(self, filename, opentype);
    } {
        if !ret.is_null() {
            self.associate(unsafe {libc::fileno(ret)}, libc::AT_FDCWD, filename);
        }
    }
    FILE * freopen (const char *filename, const char *opentype, FILE *stream) {
        fopen_parser(self, filename, opentype);
        self.close(unsafe {libc::fileno(stream)});
    } {
        if !ret.is_null() {
            self.associate(unsafe {libc::fileno(ret)}, libc::AT_FDCWD, filename);
        }
    }
    FILE * freopen64 (const char *filename, const char *opentype, FILE *stream) {
        fopen_parser(self, filename, opentype);
        self.close(unsafe {libc::fileno(stream)});
    } {
        if !ret.is_null() {
            self.associate(unsafe {libc::fileno(ret)}, libc::AT_FDCWD, filename);
        }
    }

    // We need these in case an analysis wants to use open-to-close consistency
    // https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html
    int fclose (FILE *stream) guard_call { } {
        if ret == 0 {
            self.close(unsafe {libc::fileno(stream)});
        }
    }
    int fcloseall(void) { } {
        if ret == 0 {
            self.fcloseall();
        }
    }

    // https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html
    // TODO: what to do about optional third argument: mode_t mode?
    int open (const char *filename, int flags) guard_call {
        open_parser(self, libc::AT_FDCWD, filename, flags);
    } {
        if ret != -1 {
            self.associate(ret, libc::AT_FDCWD, filename);
        }
    }
    int open64 (const char *filename, int flags) guard_call {
        open_parser(self, libc::AT_FDCWD, filename, flags);
    } {
        if ret != -1 {
            self.associate(ret, libc::AT_FDCWD, filename);
        }
    }
    int creat (const char *filename, mode_t mode) {
        self.open_read(libc::AT_FDCWD, filename);
    } {
        if ret != -1 {
            self.associate(ret, libc::AT_FDCWD, filename);
        }
    }
    int creat64 (const char *filename, mode_t mode) {
        self.open_read(libc::AT_FDCWD, filename);
    } {
        if ret != -1 {
            self.associate(ret, libc::AT_FDCWD, filename);
        }
    }
    int close (int filedes) guard_call { } {
        if ret == 0 {
            self.close(filedes);
        }
    }
    int close_range (unsigned int lowfd, unsigned int maxfd, int flags) { } {
        if ret == 0 && flags & (libc::CLOSE_RANGE_CLOEXEC as i32) == 0 {
            self.close_range(lowfd, maxfd);
        }
    }
    void closefrom (int lowfd) { } {
        self.closefrom(lowfd);
    }

    // https://linux.die.net/man/2/openat
    int openat(int dirfd, const char *pathname, int flags) {
        open_parser(self, dirfd, pathname, flags);
    } {
        if ret != -1 {
            self.associate(ret, dirfd, pathname);
        }
    }

    // https://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/baselib-openat64.html
    int openat64(int dirfd, const char *pathname, int flags) {
        open_parser(self, dirfd, pathname, flags);
    } {
        if ret != -1 {
            self.associate(ret, dirfd, pathname);
        }
    }

    // https://www.gnu.org/software/libc/manual/html_node/Duplicating-Descriptors.html
    int dup (int old) { } {
        if ret != -1 {
            self.dup_fd(old, ret);
        }
    }

    int dup2 (int old, int new) { } {
        if ret != -1 {
            self.close(new);
            self.dup_fd(old, new);
        }
    }

    // https://www.man7.org/linux/man-pages/man2/dup.2.html
    int dup3 (int old, int new) { } {
        if ret != -1 {
            self.close(new);
            self.dup_fd(old, new);
        }
    }

    // https://www.gnu.org/software/libc/manual/html_node/Control-Operations.html#index-fcntl-function
    //int fcntl (int filedes, int command, …)
    // TODO

    // https://www.gnu.org/software/libc/manual/html_node/Working-Directory.html
    int chdir (const char *filename) { } {
        if ret != -1 {
            self.chdir(filename);
        }
    }

    int fchdir (int filedes) { } {
        if ret != -1 {
            self.fchdir(filedes);
        }
    }

    // https://www.gnu.org/software/libc/manual/html_node/Opening-a-Directory.html
    DIR * opendir (const char *dirname) { } {
        if !ret.is_null() {
            let fd = unsafe {libc::dirfd(ret)};
            self.associate(fd, libc::AT_FDCWD, dirname);
            self.opendir(fd);
        }
    }

    DIR * fdopendir (int fd) { } {
        if !ret.is_null() {
            self.opendir(fd);
        }
    }

    // https://www.gnu.org/software/libc/manual/html_node/Working-with-Directory-Trees.html
    int ftw (const char *filename, __ftw_func_t func, int descriptors) {
        self.ftw(filename);
    } { }

    int ftw64 (const char *filename, __ftw64_func_t func, int descriptors) {
        self.ftw(filename);
    } { }

    int nftw (const char *filename, __nftw_func_t func, int descriptors, int flag) {
        self.ftw(filename);
    } { }

    int nftw64 (const char *filename, __nftw64_func_t func, int descriptors, int flag) {
        self.ftw(filename);
    } { }

    // https://www.gnu.org/software/libc/manual/html_node/Hard-Links.html
    int link (const char *oldname, const char *newname) {
        self.metadata_read(libc::AT_FDCWD, oldname);
        self.metadata_read(libc::AT_FDCWD, newname);
    } {
        if ret == 0 {
            self.link(libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
        }
    }

    int linkat (int oldfd, const char *oldname, int newfd, const char *newname, int flags) {
        self.metadata_read(oldfd, oldname);
        self.metadata_read(newfd, newname);
    } {
        if ret == 0 {
            self.link(oldfd, oldname, newfd, newname);
        }
    }

    // https://www.gnu.org/software/libc/manual/html_node/Symbolic-Links.html
    int symlink (const char *oldname, const char *newname) {
        self.metadata_read(libc::AT_FDCWD, oldname);
        self.metadata_read(libc::AT_FDCWD, newname);
    } {
        if ret == 0 {
            self.symlink(libc::AT_FDCWD, oldname, libc::AT_FDCWD, newname);
        }
    }

    ssize_t readlink (const char *filename, char *buffer, size_t size) { } {
        if ret == 0 {
            self.readlink(libc::AT_FDCWD, filename);
        }
    }
}

struct NullProvLogger();
impl NullProvLogger { fn new() -> Self { Self() } }
impl ProvLogger for NullProvLogger { }

struct StraceProvLogger {
    file: std::fs::File,
}
impl StraceProvLogger {
    fn new() -> Self {
        crate::globals::ENABLE_TRACE.set(false);
        let filename =
            std::env::var("PROV_TRACER_FILE")
            .unwrap_or("%p.%t.prov_trace".to_string())
            .replace("%p", std::process::id().to_string().as_str())
            .replace("%t", std::thread::current().id().as_u64().to_string().as_str());
        let file = std::fs::File::create(filename).unwrap();
        crate::globals::ENABLE_TRACE.set(true);
        Self { file }
    }
}

pub struct SemanticProvLogger {
    file: std::fs::File,
    dir: std::path::PathBuf,
    cwd: std::path::PathBuf,
    file_descriptors: std::collections::HashMap::<i32, std::path::PathBuf>,
    read_contents_and_metadata: std::collections::HashSet::<std::path::PathBuf>,
    read_metadata: std::collections::HashSet::<std::path::PathBuf>,
    copied_contents_and_metadata: std::collections::HashSet::<std::path::PathBuf>,
    copied_metadata: std::collections::HashSet::<std::path::PathBuf>,
    // TODO: handle symlinks and hardlinks
}

use std::io::Write;

impl SemanticProvLogger {
    fn normalize_path(&self, path: *const libc::c_char) -> std::path::PathBuf {
        use std::os::unix::ffi::OsStrExt;
        let mut ret = self.cwd.clone();
        ret.push(std::ffi::OsStr::from_bytes(unsafe { std::ffi::CStr::from_ptr(path) }.to_bytes()));
        ret.canonicalize().unwrap()
        // TODO: decide what kind of canonicalizing we should be doing
    }

    fn normalize_pathat(&self, dirfd: libc::c_int, path: *const libc::c_char) -> std::path::PathBuf {
        use std::os::unix::ffi::OsStrExt;
        let subpath = std::path::PathBuf::from(std::ffi::OsStr::from_bytes(unsafe { std::ffi::CStr::from_ptr(path) }.to_bytes()));
        let base = if dirfd == libc::AT_FDCWD {
            assert!(self.cwd == std::env::current_dir().unwrap());
            &self.cwd
        } else {
            self.file_descriptors.get(&dirfd).expect(UNKNOWN_FD_MSG)
        };
        std::path::Path::join(base, subpath)
        // TODO: decide what kind of canonicalizing we should be doing
    }

	fn new() -> Self {
        globals::ENABLE_TRACE.set(false);
        let filename =
            std::env::var("PROV_TRACER_FILE")
            .unwrap_or("%p.%t.prov_trace".to_string())
            .replace("%p", std::process::id().to_string().as_str())
            .replace("%t", std::thread::current().id().as_u64().to_string().as_str());
        let file = std::fs::File::create(filename).unwrap();
        let dirname = std::env::var("PROV_TRACER_DIR")
            .unwrap_or("%p.prov_files".to_string());
        globals::ENABLE_TRACE.set(true);
		Self {
            file,
            dir: std::path::PathBuf::from(dirname),
            cwd: std::env::current_dir().unwrap(),
            file_descriptors: std::collections::HashMap::new(),
            read_contents_and_metadata: std::collections::HashSet::new(),
            read_metadata: std::collections::HashSet::new(),
            copied_contents_and_metadata: std::collections::HashSet::new(),
            copied_metadata: std::collections::HashSet::new(),
        }
	}

    fn associate(&mut self, fd: libc::c_int, dirfd: libc::c_int, filename: *const libc::c_char) {
        self.file_descriptors.insert(fd, self.normalize_pathat(dirfd, filename));
    }

    fn metadata_read(&mut self, dirfd: libc::c_int, name: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, name);
        if !self.copied_metadata.contains(&path) && !self.copied_contents_and_metadata.contains(&path) {
            self.read_metadata.insert(path);
        }
    }

    fn metadata_writepart(&mut self, dirfd: libc::c_int, name: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, name);
        // note that reading contents implies reading metadta
        if self.read_metadata.contains(&path) || self.read_contents_and_metadata.contains(&path) {
            write!(self.file, "copy-metadata-if-exists {:?}", path).unwrap();
            println!("copy-metadata-if-exists {:?}", path);
            self.read_metadata.remove(&path);
            self.copied_metadata.insert(path);
        }
    }

    fn open_read(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, filename);
        if !self.copied_contents_and_metadata.contains(&path) {
            self.copied_contents_and_metadata.insert(path);
        }
    }

    fn open_writepart(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, filename);
        if self.read_contents_and_metadata.contains(&path) {
            write!(self.file, "copy-if-exists {:?}", path).unwrap();
            println!("copy-if-exists {:?}", path);
            self.read_contents_and_metadata.remove(&path);
            self.copied_contents_and_metadata.insert(path);
        } else {
            // Writing part of a file is semantically, read all of file into buffer, modify buffer, and write all of buffer into file.
            // Therefore, we consider this a read-contents operation
            self.read_contents_and_metadata.insert(path);
        }
    }

    fn open_readwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        self.open_writepart(dirfd, filename);
    }

    fn open_overwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, filename);
        if self.read_contents_and_metadata.contains(&path) {
            write!(self.file, "copy-if-exists {:?}", path).unwrap();
            println!("copy-if-exists {:?}", path);
            self.read_contents_and_metadata.remove(&path);
            self.copied_contents_and_metadata.insert(path);
        } else {
            // It is as if we copied, since this gets generated by the program
            self.copied_contents_and_metadata.insert(path);
        }
    }

    fn close(&mut self, fd: libc::c_int) {
        self.file_descriptors.remove(&fd);
    }

    fn fcloseall(&mut self) {
        self.file_descriptors.clear();
    }

    fn close_range(&mut self, lowfd: libc::c_uint, maxfd: libc::c_uint) {
        self.file_descriptors.retain(|&fd, _| !((lowfd as i32) <= fd && fd <= (maxfd as i32)));
    }

    fn closefrom(&mut self, lowfd: libc::c_int) {
        self.file_descriptors.retain(|&fd, _| fd < lowfd);
    }

    fn dup_fd(&mut self, _oldfd: libc::c_int, _newfd: libc::c_int) {
        panic!("TODO: we don't support dup_fd yet");
    }

    fn chdir(&mut self, filename: *const libc::c_char) {
        self.cwd = self.normalize_path(filename);
    }

    fn fchdir(&mut self, filedes: libc::c_int) {
        self.cwd = self.file_descriptors.get(&filedes).expect(UNKNOWN_FD_MSG).to_path_buf();
    }
    fn ftw(&mut self, filename: *const libc::c_char) { }
    fn opendir(&mut self, fd: libc::c_int) { }
    fn link(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char, newfd: libc::c_int, newname: *const libc::c_char) { }
    fn symlink(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char, newfd: libc::c_int, newname: *const libc::c_char) { }
    fn readlink(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char) { }
}

const UNKNOWN_FD_MSG: &str = "Original program would probably have crashed here, because it accesses a dirfd it never opened";

type MyProvLogger = SemanticProvLogger;

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
    // static PROV_LOGGER: std::cell::RefCell<std::mem::ManuallyDrop<MyProvLogger>> = std::cell::RefCell::new(std::mem::ManuallyDrop::new(MyProvLogger::new(&CFUNC_SIGS)));
    static PROV_LOGGER: std::cell::RefCell<DisableLoggingInDrop<MyProvLogger>> = std::cell::RefCell::new(DisableLoggingInDrop::new(MyProvLogger::new()));
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
    // match (first_char, append) {
    //     ('r', false) => prov_logger.open_read(libc::AT_FDCWD, filename),
    //     ('r', true ) => prov_logger.open_readwrite(libc::AT_FDCWD, filename),
    //     ('w', false) => prov_logger.open_overwrite(libc::AT_FDCWD, filename),
    //     ('w', true ) => prov_logger.open_overwrite(libc::AT_FDCWD, filename),
    //     ('a', false) => prov_logger.open_writepart(libc::AT_FDCWD, filename),
    //     ('a', true ) => prov_logger.open_readwrite(libc::AT_FDCWD, filename),
    //     (x, _) => panic!("Unknown opentypes {:?}", x),
    // };
}

fn open_parser(prov_logger: &mut MyProvLogger, dirfd: libc::c_int, filename: *const libc::c_char, flags: libc::c_int) {
    // if false {
    // } else if (flags & libc::O_ACCMODE) == libc::O_RDWR {
    //     if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
    //         prov_logger.open_overwrite(dirfd, filename);
    //     } else {
    //         prov_logger.open_readwrite(dirfd, filename);
    //     }
    // } else if (flags & libc::O_ACCMODE) == libc::O_RDONLY {
    //     if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
    //         // Truncates the file, which is a write
    //         // And then reads from it. Maybe someone else wrote to it since then.
    //         prov_logger.open_readwrite(dirfd, filename);
    //     } else {
    //         prov_logger.open_read(dirfd, filename);
    //     }
    // } else if (flags & libc::O_ACCMODE) == libc::O_WRONLY {
    //     if flags & libc::O_TMPFILE != 0 {
    //         prov_logger.open_overwrite(dirfd, std::ptr::null());
    //     } else if (flags & libc::O_CREAT) != 0 || (flags & libc::O_TRUNC) != 0 {
    //         prov_logger.open_overwrite(dirfd, filename);
    //     } else {
    //         prov_logger.open_writepart(dirfd, filename);
    //     }
    // } else if (flags & libc::O_ACCMODE) == libc::O_PATH {
    //     prov_logger.metadata_read(dirfd, filename);
    // }
}
