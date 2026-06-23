mod arena;
mod context;
mod ops;
mod file_info;

pub use arena::*;
pub use context::*;
pub use ops::*;
pub use file_info::*;

#[repr(C)]
pub struct CExports(Op, ProcessTreeContext, ProcessContext, ArenaHeader);

#[derive(schemars::JsonSchema)]
pub struct JSONExports(pub Op, pub ProcessTreeContext, pub AllFileInfo);
