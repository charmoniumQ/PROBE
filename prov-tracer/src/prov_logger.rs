use std::vec::Vec;

#[allow(unused_variables)]
pub trait ProvLogger {
    fn new(cfunc_sigs: &'static CFuncSigs) -> Self;
    fn log_call(&mut self, name: &'static str, args: Vec<Box<dyn std::any::Any>>, new_args: Vec<Box<dyn std::any::Any>>, ret: Box<dyn std::any::Any>) { }

    fn metadata_read(&mut self, dirfd: libc::c_int, name: *const libc::c_char) { }
    fn metadata_writepart(&mut self, dirfd: libc::c_int, name: *const libc::c_char) { }
    fn open_none     (&mut self, dirfd: libc::c_int, filename: *const libc::c_char, fd: libc::c_int) { }
    fn open_read     (&mut self, dirfd: libc::c_int, filename: *const libc::c_char, fd: libc::c_int) { }
    fn open_writepart(&mut self, dirfd: libc::c_int, filename: *const libc::c_char, fd: libc::c_int) { }
    fn open_readwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char, fd: libc::c_int) { }
    fn open_overwrite(&mut self, dirfd: libc::c_int, filename: *const libc::c_char, fd: libc::c_int) { }
    fn open_overwriteshared(&mut self, dirfd: libc::c_int, filename: *const libc::c_char, fd: libc::c_int) { }
    fn close(&mut self, fd: libc::c_int) { }
    fn fcloseall(&mut self) { }
    fn close_range(&mut self, lowfd: libc::c_uint, maxfd: libc::c_uint) { }
    fn closefrom(&mut self, lowfd: libc::c_int) { }
    fn dup_fd(&mut self, oldfd: libc::c_int, newfd: libc::c_int) { }
    fn opendir(&mut self, dirname: *const libc::c_char, dir: *const libc::DIR, dirfd: libc::c_int) { }
    fn closedir(&mut self, dir: *const libc::DIR) { }
    fn link(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char, newfd: libc::c_int, newname: *const libc::c_char) { }
    fn symlink(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char, newfd: libc::c_int, newname: *const libc::c_char) { }
    fn readlink(&mut self, oldfd: libc::c_int, oldname: *const libc::c_char) { }
}

pub type CFuncSigs = std::collections::HashMap<&'static str, CFuncSig>;

pub struct CFuncSig {
    pub return_type: CType,
    pub name: &'static str,
    pub arg_types: &'static [ArgType],
}

pub struct ArgType {
    pub arg: &'static str,
    pub ty: CType,
}

pub enum CType {
    PtrMut(CPrimType),
    PtrConst(CPrimType),
    PrimType(CPrimType),
}

pub enum CPrimType {
    Int,
    Uint,
    Char,
    File,
    ModeT,
    Void,
    Dir,
    SizeT,
    SsizeT,
}
