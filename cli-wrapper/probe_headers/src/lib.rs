mod arena;
mod context;
mod ops;

pub use arena::*;
pub use context::*;
pub use ops::*;

#[derive(schemars::JsonSchema)]
pub struct All {
    pub op: Op,
    pub process_tree_context: ProcessTreeContext,
}
