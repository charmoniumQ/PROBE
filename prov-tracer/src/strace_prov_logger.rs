use envconfig::Envconfig;
use std::io::Write;

use crate::util::short_cstr;

use crate::prov_logger::{CType, CPrimType, CFuncSigs, CFuncSig};

pub struct StraceProvLogger {
    file: std::fs::File,
}

impl crate::prov_logger::ProvLogger for StraceProvLogger {
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
		Self { file }
	}

	fn log_call(&mut self, name: &'static str) {
        write!(self.file, "{}\n", name).unwrap();
	}
    fn metadata_read(&mut self, dirfd: libc::c_int, name: *const libc::c_char) {
        write!(self.file, "  metadata_read {} {:?}\n", dirfd, short_cstr(name)).unwrap();
    }
    fn metadata_writepart(&mut self, dirfd: libc::c_int, name: *const libc::c_char) {
        write!(self.file, "  metadata_writepart {} {:?}\n", dirfd, short_cstr(name)).unwrap();
    }
    fn open_read(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        write!(self.file, "  open_read {} {:?}\n", dirfd, short_cstr(filename)).unwrap();
    }
    fn open_writepart(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        write!(self.file, "  open_writepart {} {:?}\n", dirfd, short_cstr(filename)).unwrap();
    }
    fn open_readwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        write!(self.file, "  open_readwrite {} {:?}\n", dirfd, short_cstr(filename)).unwrap();
    }
    fn open_overwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char) {
        write!(self.file, "  open_overwrite {} {:?}\n", dirfd, short_cstr(filename)).unwrap();
    }
    fn associate(&mut self, fd: libc::c_int, dirfd: libc::c_int, filename: *const libc::c_char) {
        write!(self.file, "  associate {} {:?}\n", dirfd, short_cstr(filename)).unwrap();
    }
    fn close(&mut self, fd: libc::c_int) { }
    fn fcloseall(&mut self) { }
    fn close_range(&mut self, lowfd: libc::c_uint, maxfd: libc::c_uint) { }
    fn closefrom(&mut self, lowfd: libc::c_int) { }
    fn dup_fd(&mut self, oldfd: libc::c_int, newfd: libc::c_int) { }
    fn chdir(&mut self, filename: *const libc::c_char) { }
    fn fchdir(&mut self, filedes: libc::c_int) { }
    fn ftw(&mut self, filename: *const libc::c_char) { }
    fn opendir(&mut self, fd: libc::c_int) { }
    fn link(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char, newfd: libc::c_int, newname: *const libc::c_char) { }
    fn symlink(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char, newfd: libc::c_int, newname: *const libc::c_char) { }
    fn readlink(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char) { }
}

#[allow(dead_code)]
#[derive(envconfig::Envconfig)]
struct ProvTraceConfig {
    #[envconfig(from = "PROV_TRACE_FILENAME", default = "%p.%t.prov.trace")]
    filename: String,
}

fn _cfunc_sig_args_to_string(cfunc_sig: CFuncSig, args: std::vec::Vec<Box<dyn std::any::Any>>, ret: Box<dyn std::any::Any>) -> String {
    let return_type = _ctype_to_string(ret, &cfunc_sig.return_type);
    let args: String = cfunc_sig.arg_types.iter().zip(args).map(|(arg_type, arg)| {
        format!("{}={}", arg_type.arg, _ctype_to_string(arg, &arg_type.ty))
    }).intersperse(", ".to_string()).collect();
    format!("{}({}) -> {}", cfunc_sig.name, args, return_type)
}

fn _ctype_to_string(any: Box<dyn std::any::Any>, ctype: &CType) -> String {
    match ctype {
        CType::PtrMut(prim_type) => match prim_type {
            CPrimType::Void => format!("(void*){:p}", *any.downcast_ref::<*mut libc::c_void>().unwrap()),
            CPrimType::File => format!("(FILE*){:p}", *any.downcast_ref::<*mut libc::FILE>().unwrap()),
            CPrimType::Dir  => format!("(DIR*){:p}", *any.downcast_ref::<*mut libc::DIR>().unwrap()),
            _ => "Unknown mut ptr type".to_owned(),
        },
        CType::PtrConst(prim_type) => match prim_type {
            CPrimType::Char => format!("{:?}", crate::util::short_cstr(*any.downcast_ref::<*const libc::c_char>().unwrap()).to_str().unwrap()),
            _ => "Unknown const ptr type".to_owned(),
        },
        CType::PrimType(prim_type) => match prim_type {
            CPrimType::Int => format!("{:?}", any.downcast_ref::<libc::c_int>().unwrap()),
            CPrimType::Uint => format!("{:?}", any.downcast_ref::<libc::c_uint>().unwrap()),
            CPrimType::ModeT => format!("{:?}", any.downcast_ref::<libc::mode_t>().unwrap()),
            CPrimType::FtwFuncT => format!("{:?}", any.downcast_ref::<*const libc::c_void>().unwrap()),
            CPrimType::Ftw64FuncT => format!("{:?}", any.downcast_ref::<*const libc::c_void>().unwrap()),
            CPrimType::NftwFuncT => format!("{:?}", any.downcast_ref::<*const libc::c_void>().unwrap()),
            CPrimType::Nftw64FuncT => format!("{:?}", any.downcast_ref::<*const libc::c_void>().unwrap()),
            _ => "Unknown prim type type".to_owned(),
        },
    }
}
