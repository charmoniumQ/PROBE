pub const PROBE_PATH_MAX: usize = 4096;
pub const LD_PRELOAD_VAR: &str = "LD_PRELOAD";
pub const PROBE_DIR_VAR: &str = "__PROBE_DIR";
pub const PROBE_COPY_FILES_VAR: &str = "__PROBE_COPY_FILES";
pub const PIDS_SUBDIR: &str = "pids";
pub const CONTEXT_SUBDIR: &str = "context";
pub const INODES_SUBDIR: &str = "inodes";
pub const PROCESS_TREE_CONTEXT_FILE: &str = "process_tree_context";
pub const DATA_SUBDIR: &str = "data";
pub const OPS_SUBDIR: &str = "ops";
// I would like to propagate this to C, if possible
// https://github.com/mozilla/cbindgen/issues/927

/*
 * Note that these structs get used in shared mmapped memory.
 * Pointers mess everything up because the memory can be mapped to a different virtual address in a different address space (aka process).
 * Therefore, it's easiest to hold strings as fixed-size char arrays.
 * It costs 4KiB per string.
 * That's peanuts these days.
 */
#[repr(C)]
pub struct FixedPath {
    pub bytes: [std::ffi::c_char; PROBE_PATH_MAX],
    pub len: u32,
}

impl Default for FixedPath {
    fn default() -> Self {
        Self {
            bytes: [0; PROBE_PATH_MAX],
            len: 0,
        }
    }
}

impl FixedPath {
    pub fn from_path_ref<P: AsRef<std::path::Path>>(path: P) -> Self {
        let mut output = FixedPath::default();
        let cstring = std::ffi::CString::new(path.as_ref().to_string_lossy().as_bytes())
            .expect("Path contains null byte");
        let bytes = cstring.as_bytes_with_nul();
        assert!(
            bytes.len() <= output.bytes.len(),
            "Path too long for {}-byte buffer",
            PROBE_PATH_MAX
        );
        unsafe {
            /* Should be mem-safe because we checked the length. */
            std::ptr::copy_nonoverlapping(
                bytes.as_ptr(),
                output.bytes.as_mut_ptr() as *mut u8, /* sizeof(i8) == sizeof(u8) */
                bytes.len(),
            );
        };
        /* Just in case */
        output.bytes[bytes.len()] = 0_i8;
        output.len = bytes.len() as u32 - 1 /* Exclude the null byte from length calculation */;
        output
    }
}

#[repr(C)]
pub struct ProcessTreeContext {
    pub libprobe_path: FixedPath,
    pub copy_files: CopyFiles,
}

pub fn object_to_bytes<Type: Sized>(object: &Type) -> &[u8] {
    unsafe {
        core::slice::from_raw_parts(
            (object as *const Type) as *const u8,
            core::mem::size_of::<Type>(),
        )
    }
}

#[derive(Copy, Clone, PartialEq, Eq, PartialOrd, Ord, clap::ValueEnum, Debug)]
#[repr(C)]
pub enum CopyFiles {
    None,
    Lazily,
    Eagerly,
}

#[repr(C)]
pub struct ProcessContext {
    pub epoch_no: u32,
    pub process_tree_path: FixedPath,
    pub pid_arena_path: FixedPath,
    pub enable_recording: bool,
}
