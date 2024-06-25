use color_eyre::eyre::{eyre, ContextCompat, Report, Result, WrapErr};
use rayon::iter::{ParallelBridge, ParallelIterator};
use std::{
    collections::HashMap,
    ffi::{OsStr, OsString},
    fs::{self, DirEntry, File},
    io::Write,
    mem::size_of,
    path::{Path, PathBuf},
};

use crate::{
    ffi,
    ops::{self, FfiFrom},
};

/// Arena allocator metadata placed at the beginning of allocator files by libprobe.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ArenaHeader {
    instantiation: libc::size_t,
    base_address: libc::uintptr_t,
    capacity: libc::uintptr_t,
    used: libc::uintptr_t,
}

/// This struct represents a single `ops/*.dat` arena allocator file emitted by libprobe.
pub struct OpsArena<'a> {
    // raw is needed even though it's unused since ops is a reference to it;
    // the compiler doesn't know this since it's constructed using unsafe code.
    #[allow(dead_code)]
    /// raw byte buffer of Ops arena allocator.
    raw: Vec<u8>,
    /// slice over Ops of the raw buffer.
    ops: &'a [ffi::Op],
}

impl<'a> OpsArena<'a> {
    pub fn from_bytes(bytes: Vec<u8>) -> Result<Self> {
        if bytes.len() < size_of::<ArenaHeader>() {
            return Err(eyre!(
                "Arena buffer too small, got {}, minimum size {}",
                bytes.len(),
                size_of::<ArenaHeader>()
            ));
        }

        let header = unsafe { get_header_unchecked(&bytes) };
        if header.capacity != bytes.len() {
            return Err(eyre!(
                "Invalid arena capacity, expected {}, got {}",
                header.capacity,
                bytes.len(),
            ));
        }
        if header.used > header.capacity {
            return Err(eyre!(
                "Arena size {} is greater than capacity {}",
                header.used,
                header.capacity,
            ));
        }
        if ((header.used - size_of::<ArenaHeader>()) % size_of::<ffi::Op>()) != 0 {
            return Err(eyre!(
                "Arena alignment error: used arena size minus header isn't a multiple of op size"
            ));
        }

        let count = (header.used - size_of::<ArenaHeader>()) / size_of::<ffi::Op>();

        log::debug!("[unsafe] converting Vec<u8> to &[ffi::Op] of size {}", count);
        let ops = unsafe {
            let ptr = bytes.as_ptr().add(size_of::<ArenaHeader>()) as *const ffi::Op;
            std::slice::from_raw_parts(ptr, count)
        };

        Ok(Self { raw: bytes, ops })
    }

    pub fn decode(self, ctx: &ArenaContext) -> Result<Vec<ops::Op>> {
        self.ops
            .iter()
            .map(|x| ops::Op::ffi_from(x, ctx))
            .collect::<Result<Vec<_>>>()
            .wrap_err("Failed to decode arena ops")
    }
}

/// This struct represents a single `data/*.dat` arena allocator file emitted by libprobe.
pub struct DataArena {
    header: ArenaHeader,
    raw: Vec<u8>,
}

impl DataArena {
    pub fn from_bytes(bytes: Vec<u8>) -> Result<Self> {
        if bytes.len() < size_of::<ArenaHeader>() {
            return Err(eyre!(
                "Arena buffer too small, got {}, minimum size {}",
                bytes.len(),
                size_of::<ArenaHeader>()
            ));
        }
        let header = unsafe { get_header_unchecked(&bytes) };
        if header.capacity != bytes.len() {
            return Err(eyre!(
                "Invalid arena capacity, expected {}, got {}",
                header.capacity,
                bytes.len(),
            ));
        }
        if header.used > header.capacity {
            return Err(eyre!(
                "Arena size {} is greater than capacity {}",
                header.used,
                header.capacity,
            ));
        }
        Ok(Self { header, raw: bytes })
    }

    pub fn try_deref(&self, ptr: usize) -> Option<*const u8> {
        match ptr >= self.header.base_address
            && ptr <= (self.header.base_address + self.header.used)
        {
            false => None,
            true => Some(unsafe { self.raw.as_ptr().add(ptr - self.header.base_address) }),
        }
    }
}

/// this struct represents a `<TID>/data` directory from libprobe.
pub struct ArenaContext(pub Vec<DataArena>);

impl ArenaContext {
    pub fn try_deref(&self, ptr: usize) -> Option<*const u8> {
        for vec in self.0.iter() {
            if let Some(x) = vec.try_deref(ptr) {
                return Some(x);
            }
        }
        None
    }
}

/// Parse the front of a raw byte buffer into a libprobe arena header
///
/// # Safety:
/// Invoking this function on any byte buffer smaller than [`std::mem::size_of<ArenaHeader>()`]
/// bytes is undefined behavior (best case a segfault). Invoking this method on a byte buffer
/// that's not a valid libprobe arena will produce garbage values that should not be used.
unsafe fn get_header_unchecked(bytes: &[u8]) -> ArenaHeader {
    let ptr = bytes as *const [u8] as *const ArenaHeader;
    log::debug!("[unsafe] converting byte buffer into ArenaHeader");
    unsafe {
        ArenaHeader {
            instantiation: (*ptr).instantiation,
            base_address: (*ptr).base_address,
            capacity: (*ptr).capacity,
            used: (*ptr).used,
        }
    }
}

/// Gets the filename from a path and returns it parsed as an integer.
///
/// errors if the path has no filename or the filename can't be parsed as an integer.
fn filename_numeric<P: AsRef<Path>>(dir: P) -> Result<usize> {
    let filename = dir
        .as_ref()
        .file_name()
        .ok_or_else(|| eyre!("'{}' has no filename", dir.as_ref().to_string_lossy()))?;

    filename
        .to_str()
        .ok_or_else(|| eyre!("filename '{}' not valid UTF-8", filename.to_string_lossy()))?
        .parse::<usize>()
        .wrap_err(format!(
            "unable to convert filename '{}' to integer",
            filename.to_string_lossy()
        ))
}

/// Recursively parse a TID libprobe arena allocator directory from `in_dir` and write it in
/// serialized format to `out_dir`.
///
/// This function parses a TID directory in 6 steps:
///
/// 1. Output file is created.
/// 2. Paths of sub-directory are parsed into a [`HashMap`].
/// 3. `data` directory is is read and parsed into [`DataArena`]s which are then parsed into an
///    [`ArenaContext`].
/// 4. `ops` directory is read and parsed into [`OpsArena`]s.
/// 5. [`OpsArena`]s are parsed into which are then parsed into [`ops::Op`]s using the
///    [`ArenaContext`].
/// 6. [`ops::Op`]s are serialized into json and written line-by-line into the output directory.
///
/// (steps 5 & 6 are done with iterators to reduce unnecessary memory allocations)
fn parse_tid<P1: AsRef<Path>, P2: AsRef<Path>>(in_dir: P1, out_dir: P2) -> Result<()> {
    fn try_files_from_arena_dir<P: AsRef<Path>>(dir: P) -> Result<Vec<PathBuf>> {
        match fs::read_dir(&dir) {
            Ok(x) => x
                .map(|x| {
                    x.map(|x| x.path())
                        .wrap_err("Error reading DirEntry from arena directory")
                })
                .collect::<Result<Vec<_>, _>>(),
            Err(e) => Err(Report::from(e).wrap_err("Error opening arena directory")),
        }
    }

    // STEP 1
    let tid = filename_numeric(&in_dir)?;
    let mut outfile = {
        let mut path = out_dir.as_ref().to_owned();
        path.push(tid.to_string());
        File::create_new(path).wrap_err("Failed to create TID output file")?
    };

    // STEP 2
    let paths = fs::read_dir(&in_dir)
        .wrap_err(format!(
            "Error reading directory '{}'",
            in_dir.as_ref().to_string_lossy()
        ))?
        .filter_map(|x| match x {
            Ok(x) => Some((x.file_name(), x)),
            Err(e) => {
                log::warn!("Error reading DirEntry in TID directory: {}", e);
                None
            }
        })
        .collect::<HashMap<OsString, DirEntry>>();

    // STEP 3
    let ctx = ArenaContext(
        try_files_from_arena_dir(
            paths
                .get(OsStr::new("data"))
                .wrap_err("Missing data directory from TID directory")?
                .path(),
        )?
        .into_iter()
        .map(|x| {
            DataArena::from_bytes(
                std::fs::read(x).wrap_err("Failed to read file from data directory")?,
            )
        })
        .collect::<Result<Vec<_>, _>>()?,
    );

    // STEP 4
    try_files_from_arena_dir(
        paths
            .get(OsStr::new("ops"))
            .wrap_err("Missing ops directory from TID directory")?
            .path(),
    )?
    // STEP 5
    .into_iter()
    .map(|x| {
        std::fs::read(x)
            .wrap_err("Failed to read file from ops directory")
            .and_then(|x| {
                OpsArena::from_bytes(x)
                    .wrap_err("Error constructing OpsArena")?
                    .decode(&ctx)
                    .wrap_err("Error decoding OpsArena")
            })
    })
    // STEP 6
    .try_for_each(|x| {
        for op in x? {
            outfile
                .write_all(
                    serde_json::to_string(&op)
                        .wrap_err("Unable to serialize Op")?
                        .as_bytes(),
                )
                .wrap_err("Failed to write serialized Op to tempfile")?;
            outfile
                .write_all("\n".as_bytes())
                .wrap_err("Failed to write newline deliminator to tempfile")?;
        }

        Ok::<(), Report>(())
    })?;

    Ok(())
}

/// Recursively parse a ExecEpoch libprobe arena allocator directory from `in_dir` and write it in
/// serialized format to `out_dir`.
///
/// This function calls [`parse_tid()`] on each sub-directory in `in_dir`.
fn parse_exec_epoch<P1: AsRef<Path>, P2: AsRef<Path>>(in_dir: P1, out_dir: P2) -> Result<()> {
    let epoch = filename_numeric(&in_dir)?;

    let dir = {
        let mut path = out_dir.as_ref().to_owned();
        path.push(epoch.to_string());
        path
    };

    fs::create_dir(&dir).wrap_err("Failed to create ExecEpoch output directory")?;

    fs::read_dir(in_dir)
        .wrap_err("Error opening ExecEpoch directory")?
        // .par_bridge()
        .try_for_each(|x| {
            parse_tid(
                x.wrap_err("Error reading DirEntry from ExecEpoch directory")?
                    .path(),
                &dir,
            )
        })?;

    Ok(())
}

/// Recursively parse a PID libprobe arena allocator directory from `in_dir` and write it in
/// serialized format to `out_dir`.
///
/// This function calls [`parse_exec_epoch()`] on each sub-directory in `in_dir`.
fn parse_pid<P1: AsRef<Path>, P2: AsRef<Path>>(in_dir: P1, out_dir: P2) -> Result<()> {
    let pid = filename_numeric(&in_dir)?;

    let dir = {
        let mut path = out_dir.as_ref().to_owned();
        path.push(pid.to_string());
        path
    };

    fs::create_dir(&dir).wrap_err("Failed to create ExecEpoch output directory")?;

    fs::read_dir(in_dir)
        .wrap_err("Error opening PID directory")?
        // .par_bridge()
        .try_for_each(|x| {
            parse_exec_epoch(
                x.wrap_err("Error reading DirEntry from PID directory")?
                    .path(),
                &dir,
            )
        })?;

    Ok(())
}

/// Recursively parse a top-level libprobe arena allocator directory from `in_dir` and write it in
/// serialized format to `out_dir`.
///
/// This function calls [`parse_pid()`] on each sub-directory in `in_dir` **in parallel**.
pub fn parse_arena_dir<P1: AsRef<Path>, P2: AsRef<Path> + Sync>(
    in_dir: P1,
    out_dir: P2,
) -> Result<()> {
    fs::read_dir(in_dir)
        .wrap_err("Error opening Arena directory")?
        .par_bridge()
        .try_for_each(|x| {
            parse_pid(
                x.wrap_err("Error reading DirEntry from Arena directory")?
                    .path(),
                &out_dir,
            )
        })?;

    Ok(())
}
