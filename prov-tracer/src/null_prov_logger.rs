use crate::prov_logger::{ProvLogger, CFuncSigs};

pub struct NullProvLogger { }
impl ProvLogger for NullProvLogger {
    fn new(_: &'static CFuncSigs) -> Self { NullProvLogger { } }
}
