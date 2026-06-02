mod arena;
mod context;
mod ops;

pub use arena::*;
pub use context::*;
pub use ops::*;

#[repr(C)]
pub struct CExports(Op, ProcessTreeContext, ProcessContext, ArenaHeader);

#[derive(schemars::JsonSchema)]
pub struct JSONExports(pub Op, pub ProcessTreeContext);
