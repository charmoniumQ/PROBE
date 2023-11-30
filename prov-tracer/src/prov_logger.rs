pub trait ProvLogger {
    fn new() -> Self;
	fn open64(&self, path: *const libc::c_char, oflag: libc::c_int, ret: libc::c_int);
	fn close(&self, fd: libc::c_int, ret: libc::c_int);
    fn fork(&self, ret: libc::c_int);
}

thread_local! {
    pub static LOG_OPEN64: std::cell::Cell<bool> = std::cell::Cell::new(true);
}
