#![deny(unsafe_op_in_unsafe_fn)]

use color_eyre::eyre::{eyre, ContextCompat, Report, Result, WrapErr};
use rayon::iter::{ParallelBridge, ParallelIterator};
use serde::{Deserialize, Serialize};
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
    ops::{self, DecodeFfi},
};

#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ArenaHeader {
    instantiation: libc::size_t,
    base_address: libc::uintptr_t,
    capacity: libc::uintptr_t,
    used: libc::uintptr_t,
}

pub struct OpsArena<'a> {
    // raw is needed even though it's unused since ops is a reference to it;
    // the compiler doesn't know this since it's constructed using unsafe code.
    #[allow(dead_code)]
    raw: Vec<u8>,
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

        let ops = unsafe {
            let ptr = bytes.as_ptr().add(size_of::<ArenaHeader>()) as *const ffi::Op;
            std::slice::from_raw_parts(ptr, count)
        };

        Ok(Self { raw: bytes, ops })
    }

    pub fn decode(self, ctx: &ArenaContext) -> Result<Vec<ops::Op>> {
        self.ops
            .iter()
            .map(|x| ops::Op::decode(x, ctx))
            .collect::<Result<Vec<_>>>()
            .wrap_err("Failed to decode arena ops")
    }
}

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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArenaTree(HashMap<usize, HashMap<usize, HashMap<usize, ops::Op>>>);

/// # Safety:
/// invoking this function on any byte buffer that is not a valid libprobe
/// arena is undefined behavior.
unsafe fn get_header_unchecked(bytes: &[u8]) -> ArenaHeader {
    let ptr = bytes as *const [u8] as *const ArenaHeader;
    unsafe {
        ArenaHeader {
            instantiation: (*ptr).instantiation,
            base_address: (*ptr).base_address,
            capacity: (*ptr).capacity,
            used: (*ptr).used,
        }
    }
}

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

    let tid = filename_numeric(&in_dir)?;
    let mut outfile = {
        let mut path = out_dir.as_ref().to_owned();
        path.push(tid.to_string());
        File::create_new(path).wrap_err("Failed to create TID output file")?
    };

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

    let data = try_files_from_arena_dir(
        paths
            .get(OsStr::new("data"))
            .wrap_err("Missing data directory from TID directory")?
            .path(),
    )?
    .into_iter()
    .map(|x| {
        DataArena::from_bytes(std::fs::read(x).wrap_err("Failed to read file from data directory")?)
    })
    .collect::<Result<Vec<_>, _>>()?;

    let ctx = ArenaContext(data);

    try_files_from_arena_dir(
        paths
            .get(OsStr::new("ops"))
            .wrap_err("Missing ops directory from TID directory")?
            .path(),
    )?
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
