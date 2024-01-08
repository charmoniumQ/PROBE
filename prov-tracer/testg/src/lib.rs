static _CALL_LOGGER: std::sync::OnceLock<VerboseCallLogger> = std::sync::OnceLock::new();

fn call_logger() -> &'static VerboseCallLogger {
    _CALL_LOGGER.get_or_init(|| VerboseCallLogger::new())
}

redhook::hook! {
    unsafe fn open(pathname: *const libc::c_char, flags: libc::c_int) -> libc::c_int => traced_open {
        print!(
            "(processing open :path {:?} :flags {:?} ",
            unsafe { String::from_utf8_lossy(std::ffi::CStr::from_ptr(pathname).to_bytes()).to_string() },
            flags,
        );
        call_logger().log("open");
        let ret = redhook::real!(open)(pathname, flags);
        println!(":ret {:?})", ret);
        ret
    }
}

struct VerboseCallLogger {}
impl VerboseCallLogger {
    fn new() -> Self {
        unsafe {print!("(VerboseCallLogger::new {} {}) ", libc::getpid(), libc::gettid())};
        Self { }
    }
    fn log(&self, name: &'static str) {
        print!("(VerboseCallLogger::log {}) ", name);
    }
}
impl Drop for VerboseCallLogger {
    fn drop(&mut self) {
        println!("(VerboseCallLogger::drop)");
    }
}

#[ctor::ctor]
fn foo() {
    unsafe { println!("(ctor {} {})", libc::getpid(), libc::gettid()) };
}
