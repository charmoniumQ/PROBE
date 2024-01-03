use envconfig::Envconfig;
use std::os::unix::ffi::OsStrExt;
use std::io::Write;

use crate::prov_logger::{CType, CPrimType, CFuncSigs};

const UNKNOWN_FD_MSG: &str = "Original program would probably have crashed here, because it accesses a dirfd it never opened";

#[derive(envconfig::Envconfig)]
struct ProvTraceConfig {
    #[envconfig(from = "PROV_TRACE_FILENAME", default = "%p.%t.prov.trace")]
    filename: String,

    #[envconfig(from = "PROV_TRACE_DIR", default = "%p.prov.trace")]
    dirname: String,
}

pub struct SemanticProvLogger {
    file: std::fs::File,
    dir: std::path::PathBuf,
    cwd: std::path::PathBuf,
    file_descriptors: std::collections::HashMap::<i32, std::path::PathBuf>,
    read_contents: std::collections::HashSet::<std::path::PathBuf>,
    read_metadata: std::collections::HashSet::<std::path::PathBuf>,
    copied_contents: std::collections::HashSet::<std::path::PathBuf>,
    copied_metadata: std::collections::HashSet::<std::path::PathBuf>,
    // TODO: handle symlinks and hardlinks
}

impl SemanticProvLogger {
    fn normalize_path(&self, path: *const libc::c_char) -> std::path::PathBuf {
        std::path::absolute(std::path::PathBuf::from(std::ffi::OsStr::from_bytes(unsafe { std::ffi::CStr::from_ptr(path) }.to_bytes()))).unwrap()
    }

    fn normalize_pathat(&self, dirfd: libc::c_int, path: *const libc::c_char) -> std::path::PathBuf {
        let subpath = std::path::PathBuf::from(std::ffi::OsStr::from_bytes(unsafe { std::ffi::CStr::from_ptr(path) }.to_bytes()));
        let base = if dirfd == libc::AT_FDCWD {
            &self.cwd
        } else {
            self.file_descriptors.get(&dirfd).expect(UNKNOWN_FD_MSG)
        };
        std::path::Path::join(base, subpath)
    }
}

impl crate::prov_logger::ProvLogger for SemanticProvLogger {
	fn new(_cfunc_sigs: &'static CFuncSigs) -> Self {
        crate::globals::ENABLE_TRACE.set(false);
        let config = ProvTraceConfig::init_from_env().unwrap();
		let pid = (unsafe { libc::getpid() }).to_string();
        let tid = (unsafe { libc::gettid() }).to_string();
        let filename =
            config.filename
                  .replace("%p", &pid)
                  .replace("%t", &tid)
            ;
        let file = std::fs::File::create(filename).unwrap();
        crate::globals::ENABLE_TRACE.set(true);
		Self {
            file,
            dir: std::path::PathBuf::from(config.dirname),
            cwd: std::env::current_dir().unwrap(),
            file_descriptors: std::collections::HashMap::new(),
            read_contents: std::collections::HashSet::new(),
            read_metadata: std::collections::HashSet::new(),
            copied_contents: std::collections::HashSet::new(),
            copied_metadata: std::collections::HashSet::new(),
        }
	}

	fn log_call(
		&mut self,
        _name: &'static str,
        _args: Vec<Box<dyn std::any::Any>>,
        _new_args: Vec<Box<dyn std::any::Any>>,
        _ret: Box<dyn std::any::Any>,
	) { }

    fn metadata_read(&mut self, dirfd: libc::c_int, name: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, name);
        if !self.copied_metadata.contains(&path) && !self.copied_contents.contains(&path) {
            self.read_metadata.insert(path);
        }
    }

    fn metadata_writepart(&mut self, dirfd: libc::c_int, name: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, name);
        // note that reading contents implies reading metadta
        if self.read_metadata.contains(&path) || self.read_contents.contains(&path) {
            write!(self.file, "copy-metadata {:?}", path).unwrap();
            self.read_metadata.remove(&path);
            self.copied_metadata.insert(path);
        }
    }

    fn open_read(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, filename);
        if !self.copied_contents.contains(&path) {
            self.copied_contents.insert(path);
        }
    }

    fn open_writepart(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, filename);
        if self.read_contents.contains(&path) {
            write!(self.file, "copy {:?}", path).unwrap();
            self.read_contents.remove(&path);
            self.copied_contents.insert(path);
        } else {
            // Writing part of a file is semantically, read all of file into buffer, modify buffer, and write all of buffer into file.
            // Therefore, we consider this a read-contents operation
            self.read_contents.insert(path);
        }
    }

    fn open_readwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, filename);
        if self.read_contents.contains(&path) {
            write!(self.file, "copy {:?}", path).unwrap();
            self.read_contents.remove(&path);
            self.copied_contents.insert(path);
        } else {
            self.read_contents.insert(path);
        }
    }

    fn open_overwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        let path = self.normalize_pathat(dirfd, filename);
        if self.read_contents.contains(&path) {
            write!(self.file, "copy {:?}", path).unwrap();
            self.read_contents.remove(&path);
            self.copied_contents.insert(path);
        } else {
            // It is as if we copied, since this gets generated by the program
            self.copied_contents.insert(path);
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
}
