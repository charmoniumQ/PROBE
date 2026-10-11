mod arena;
mod context;
mod file_info;
mod ops;

pub use arena::*;
pub use context::*;
pub use file_info::*;
pub use ops::*;

#[repr(C)]
pub struct CExports(Op, ProcessTreeContext, ProcessContext, ArenaHeader);

#[derive(schemars::JsonSchema)]
pub struct JSONExports(pub Op, pub ProcessTreeContext, pub AllFileInfo);
