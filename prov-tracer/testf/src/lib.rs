redhook::hook! {
    unsafe fn open(pathname: *const libc::c_char, flags: libc::c_int) -> libc::c_int => traced_open {
        print!(
            "(processing open :path {:?} :flags {:?} ",
            unsafe { String::from_utf8_lossy(std::ffi::CStr::from_ptr(pathname).to_bytes()).to_string() },
            flags,
        );
        CALL_LOGGER.with_borrow_mut(|call_logger| call_logger.log("open"));
        let ret = redhook::real!(open)(pathname, flags);
        println!(":ret {:?})", ret);
        ret
    }
}

struct VerboseCallLogger {}
impl VerboseCallLogger {
    fn new() -> Self {
        print!("(VerboseCallLogger::new)");
        Self { }
    }
    fn log(&mut self, name: &'static str) {
        print!("(VerboseCallLogger::log {}) ", name);
    }
}


thread_local! {
    static CALL_LOGGER:
    std::cell::RefCell<VerboseCallLogger> = std::cell::RefCell::new(VerboseCallLogger::new());
}
