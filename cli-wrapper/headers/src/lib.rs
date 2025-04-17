pub const PROBE_PATH_MAX: usize = 4096;
pub const LD_PRELOAD_VAR: &str = "LD_PRELOAD";
pub const PROBE_DIR_VAR: &str = "PROBE_DIR";
pub const PROBE_COPY_FILES_VAR: &str = "PROBE_COPY_FILES";
pub const PIDS_SUBDIR: &str = "pids";
pub const CONTEXT_SUBDIR: &str = "context";
pub const INODES_SUBDIR: &str = "inodes";
pub const PROCESS_TREE_CONTEXT_FILE: &str = "process_tree_context";
pub const DATA_SUBDIR: &str = "data";
pub const OPS_SUBDIR: &str = "ops";
// I would like to propagate this to C, if possible
// https://github.com/mozilla/cbindgen/issues/927

#[derive(Copy, Clone, PartialEq, Eq, PartialOrd, Ord, clap::ValueEnum, Debug)]
#[repr(C)]
pub enum CopyFiles {
    None,
    Lazily,
    Eagerly,
}
