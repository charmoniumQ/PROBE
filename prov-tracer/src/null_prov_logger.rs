use envconfig::Envconfig;
use std::io::Write;

use crate::prov_logger::{CType, CPrimType, CFuncSigs};
use crate::ProvLogger;

pub struct NullProvLogger {
    file: std::fs::File,
}

impl ProvLogger for NullProvLogger {
    fn new(_cfunc_sigs: &'static CFuncSigs) -> Self {
        crate::globals::ENABLE_TRACE.set(false);
		let pid = (unsafe { libc::getpid() }).to_string();
        let tid = (unsafe { libc::gettid() }).to_string();
        let filename =
            "%p.%t.prov.trace"
            .replace("%p", &pid)
            .replace("%t", &tid)
            ;
        let file = std::fs::File::create(filename).unwrap();
        crate::globals::ENABLE_TRACE.set(true);
        NullProvLogger { file }
    }
	fn log_call(
		&mut self,
        _name: &'static str,
        _args: Vec<Box<dyn std::any::Any>>,
        _new_args: Vec<Box<dyn std::any::Any>>,
        _ret: Box<dyn std::any::Any>,
	) {
	}
}
