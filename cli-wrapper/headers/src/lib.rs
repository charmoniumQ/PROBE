use serde::Serialize;

pub const PROBE_PATH_MAX: usize = 4096;
pub const LD_PRELOAD_VAR: &str = "LD_PRELOAD";
pub const PROBE_DIR_VAR: &str = "PROBE_DIR";
pub const PIDS_SUBDIR: &str = "pids";
pub const CONTEXT_SUBDIR: &str = "context";
pub const INODES_SUBDIR: &str = "inodes";
pub const PROCESS_TREE_CONTEXT_FILE: &str = "process_tree_context";
pub const DATA_SUBDIR: &str = "data";
pub const OPS_SUBDIR: &str = "ops";
// I would like to propagate this to C, if possible
// https://github.com/mozilla/cbindgen/issues/927

/// cbindgen:prefix-with-name
#[derive(Copy, Clone, PartialEq, Eq, PartialOrd, Ord, clap::ValueEnum, Debug, serde::Serialize)]
#[repr(C)]
pub enum CopyFiles {
    None,
    Lazily,
    Eagerly,
}

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

#[repr(C)]
#[derive(serde::Serialize)]
pub struct ProcessTreeContext {
    pub libprobe_path: FixedPath,
    pub copy_files: CopyFiles,
    pub parent_of_root: u32,
}

#[repr(C)]
pub struct ProcessContext {
    pub epoch_no: u32,
    pub process_tree_path: FixedPath,
    pub pid_arena_path: FixedPath,
    pub enable_recording: bool,
}

impl Default for FixedPath {
    fn default() -> Self {
        Self {
            bytes: [0; PROBE_PATH_MAX],
            len: 0,
        }
    }
}

impl Serialize for FixedPath {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        if self.len as usize >= self.bytes.len() {
            Err(serde::ser::Error::custom("Length too long for fixed path"))
        } else {
            let u8_slice = unsafe {
                std::slice::from_raw_parts(self.bytes.as_ptr() as *const u8, self.len as usize)
            };
            match std::str::from_utf8(u8_slice).map(|s| s.to_string()) {
                Ok(string) => serializer.serialize_str(&string),
                Err(_) => serializer.serialize_bytes(u8_slice),
            }
        }
    }
}

impl FixedPath {
    pub fn from_path_ref<P: AsRef<std::path::Path>>(
        path: P,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let mut output = FixedPath::default();
        let cstring =
            std::ffi::CString::new(path.as_ref().to_string_lossy().as_bytes()).map_err(Box::new)?;
        let bytes = cstring.as_bytes_with_nul();
        if bytes.len() >= output.bytes.len() {
            Err("Path too long for fixed buffer".into())
        } else {
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
            Ok(output)
        }
    }
}

pub fn object_to_bytes<Type: Sized>(object: &Type) -> &[u8] {
    unsafe {
        core::slice::from_raw_parts(
            (object as *const Type) as *const u8,
            core::mem::size_of::<Type>(),
        )
    }
}

pub fn object_from_bytes<Type: Sized>(mut bytes: Vec<u8>) -> Option<Box<Type>> {
    let ptr = bytes.as_mut_ptr();
    if bytes.len() < std::mem::size_of::<Type>() || ptr as usize % align_of::<Type>() != 0 {
        None
    } else {
        Some(unsafe { Box::from_raw(ptr as *mut Type) })
    }
}
