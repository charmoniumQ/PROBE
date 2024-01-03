use envconfig::Envconfig;
use std::io::Write;

use crate::prov_logger::{CType, CPrimType, CFuncSigs};
use crate::ProvLogger;

pub struct NullProvLogger { }
impl ProvLogger for NullProvLogger {
    fn new(_cfunc_sigs: &'static CFuncSigs) -> Self {
        Self { }
    }
	fn log_call(
		&mut self,
        _name: &'static str,
        _args: Vec<Box<dyn std::any::Any>>,
        _new_args: Vec<Box<dyn std::any::Any>>,
        _ret: Box<dyn std::any::Any>,
	) { }
}
