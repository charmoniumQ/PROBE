use std::{
    ffi::OsString,
    fs::{self, File},
    os::unix::process::ExitStatusExt,
    path::{Path, PathBuf},
    process::ExitStatus,
    thread,
    time::Duration,
};

use color_eyre::eyre::{bail, eyre, Result, WrapErr};
use flate2::Compression;

use crate::transcribe;

// TODO: modularize and improve ergonomics (maybe expand builder pattern?)

/// create a probe record directory from command arguments
pub fn record_no_transcribe(
    output: Option<PathBuf>,
    overwrite: bool,
    gdb: bool,
    debug: bool,
    copy_files: probe_headers::CopyFiles,
    cmd: Vec<OsString>,
) -> Result<ExitStatus> {
    let output = match output {
        Some(x) => x,
        None => PathBuf::from("probe_log"),
    };

    if output.exists() {
        if overwrite {
            bail!("output {:?} already exists", &output);
        } else if output.is_dir() {
            fs_extra::dir::remove(&output)?;
        } else {
            fs_extra::file::remove(&output)?;
        }
    }

    let (status, dir) = Recorder::new(cmd)
        .gdb(gdb)
        .debug(debug)
        .copy_files(copy_files)
        .record()
        .wrap_err("Recorder::record")?;

    fs_extra::dir::move_dir(&dir, &output, &fs_extra::dir::CopyOptions::new()).wrap_err(eyre!(
        "moving {:?} to {:?}",
        &dir,
        &output
    ))?;

    Ok(status)
}

/// create a probe log file from command arguments
pub fn record_transcribe(
    output: Option<PathBuf>,
    overwrite: bool,
    gdb: bool,
    debug: bool,
    copy_files: probe_headers::CopyFiles,
    cmd: Vec<OsString>,
) -> Result<ExitStatus> {
    let output = match output {
        Some(x) => x,
        None => PathBuf::from("probe_log"),
    };

    if output.exists() {
        if overwrite {
            bail!("output {:?} already exists", &output);
        } else if output.is_dir() {
            fs_extra::dir::remove(&output)?;
        } else {
            fs_extra::file::remove(&output)?;
        }
    }

    let file = File::create_new(&output).wrap_err("Failed to create output file")?;

    let mut tar = tar::Builder::new(flate2::write::GzEncoder::new(file, Compression::default()));

    let (status, record_dir) = Recorder::new(cmd)
        .gdb(gdb)
        .debug(debug)
        .copy_files(copy_files)
        .record()?;

    match transcribe::transcribe(&record_dir, &mut tar) {
        Ok(_) => (),
        Err(e) => {
            log::error!(
                "Error transcribing record directory, saving directory '{}'",
                record_dir.as_ref().to_string_lossy()
            );
            std::mem::forget(record_dir);
            return Err(e).wrap_err("Failed to transcirbe record directory");
        }
    };

    Ok(status)
}

/// Builder for running processes under provenance.
// TODO: extract this into the library part of this project
#[derive(Debug)]
pub struct Recorder {
    gdb: bool,
    debug: bool,
    copy_files: probe_headers::CopyFiles,
    cmd: Vec<OsString>,
}

impl Recorder {
    /// runs the built recorder, on success returns the PID of launched process and the TempDir it
    /// was recorded into
    pub fn record(self) -> Result<(ExitStatus, tempfile::TempDir)> {
        // reading and canonicalizing path to libprobe
        let libprobe_path = fs::canonicalize(match std::env::var_os("PROBE_LIB") {
            Some(x) => PathBuf::from(x),
            None => return Err(eyre!("couldn't find libprobe, are you using the wrapper?")),
        })
        .wrap_err("unable to canonicalize libprobe path")?
        .join(if self.debug {
            log::debug!("Using debug version of libprobe");
            "libprobe.dbg.so"
        } else {
            "libprobe.so"
        });

        // append any existing LD_PRELOAD overrides; libprobe needs to be explicitly converted from
        // a PathBuf to a OsString because PathBuf::push() automatically adds path separators which
        // is incorrect here.
        let ld_preload = if let Some(previous_ld_preload) = std::env::var_os("LD_PRELOAD") {
            concat_osstrings([(&libprobe_path).into(), ":".into(), previous_ld_preload])
        } else {
            (&libprobe_path).into()
        };

        let self_bin =
            std::env::current_exe().wrap_err("Failed to get path to current executable")?;

        let record_dir = tempfile::TempDir::new()?;

        /* We start `probe __exec $cmd` instead of `$cmd`
         * This is because PROBE is not able to capture the arguments of the very first process, but it does capture the arguments of any subsequent exec(...).
         * Therefore, the "root process" is env, and the user's $cmd is exec(...)-ed.
         * We could change this by adding argv and environ to InitProcessOp, but I think this solution is more elegant.
         * Since the root process has special quirks, it should not be user's `$cmd`.
         * */
        fs::create_dir(record_dir.path().join(probe_headers::PIDS_SUBDIR))?;
        fs::create_dir(record_dir.path().join(probe_headers::CONTEXT_SUBDIR))?;
        fs::create_dir(record_dir.path().join(probe_headers::INODES_SUBDIR))?;

        let ptc = probe_headers::ProcessTreeContext {
            libprobe_path: probe_headers::FixedPath::from_path_ref(libprobe_path)
                .map_err(|e| eyre!("{e:?}"))?,
            copy_files: self.copy_files,
            parent_of_root: std::process::id(),
        };

        /* Check round-trip-ability */
        let ptc_bytes = probe_headers::object_to_bytes(ptc.clone());
        assert!(ptc == probe_headers::object_from_bytes(ptc_bytes.clone()));

        fs::write(
            record_dir
                .path()
                .join(probe_headers::PROCESS_TREE_CONTEXT_FILE),
            ptc_bytes,
        )?;

        let mut child = if self.gdb {
            std::process::Command::new("gdb")
                .arg(concat_osstrings([
                    OsString::from("--init-eval-command=set environment "),
                    OsString::from(probe_headers::LD_PRELOAD_VAR),
                    OsString::from("="),
                    ld_preload.clone(),
                ]))
                .arg(concat_osstrings([
                    OsString::from("--init-eval-command=set environment "),
                    OsString::from(probe_headers::PROBE_DIR_VAR),
                    OsString::from("="),
                    record_dir.path().into(),
                ]))
                .arg("--init-eval-command=set environment LD_DEBUG=all")
                .arg("--args")
                .arg(self_bin)
                .arg("__exec")
                .args(&self.cmd)
                .spawn()
                .wrap_err("Failed to launch gdb")?
        } else {
            std::process::Command::new(self_bin)
                .arg("__exec")
                .args(self.cmd)
                .env(probe_headers::LD_PRELOAD_VAR, ld_preload)
                // .envs((if self.debug { vec![("LD_DEBUG", "ALL")] } else {vec![]}).into_iter())
                .env(
                    probe_headers::PROBE_DIR_VAR,
                    OsString::from(&record_dir.path()),
                )
                .spawn()
                .wrap_err("Failed to launch child process")?
        };

        if !self.gdb {
            // without this the child process typically won't have written it's first op by the
            // time we do our sanity check, since we're about to wait on child anyway, this isn't a
            // big deal.
            thread::sleep(Duration::from_millis(50));

            match Path::read_dir(record_dir.path()) {
                Ok(x) => {
                    let any_files = x
                        .into_iter()
                        .try_fold(false, |_, x| x.map(|x| x.path().exists()))?;
                    if !any_files {
                        log::warn!(
                            "No arena files detected after 50ms, \
                            something is wrong, you should probably abort!"
                        );
                    }
                }
                Err(e) => {
                    return Err(e).wrap_err(
                        "Unable to read record directory during post-startup sanity check",
                    )
                }
            }
        }

        // OPTIMIZE: consider background serialization of ops as threads/processes exit instead of
        // waiting until the end; large increase to complexity but potentially huge gains.
        let exit = child.wait().wrap_err("Failed to await child process")?;
        if !exit.success() {
            match exit.code() {
                Some(code) => log::warn!("Recorded process exited with code {code}"),
                None => match exit.signal() {
                    Some(sig) => match crate::util::sig_to_name(sig) {
                        Some(name) => log::warn!("Recorded process exited with signal {name}"),
                        None => {
                            if sig < libc::SIGRTMAX() {
                                log::warn!("Recorded process exited with realtime signal {sig}");
                            } else {
                                log::warn!("Recorded process exited with unknown signal {sig}");
                            }
                        }
                    },
                    None => log::warn!("Recorded process exited with unknown error"),
                },
            }
        }

        Ok((exit, record_dir))
    }

    /// Create new [`Recorder`] from a command and the directory where it should write the probe
    /// record.
    ///
    /// `cmd[0]` will be used as the command while `cmd[1..]` will be used as the arguments.
    pub fn new(cmd: Vec<OsString>) -> Self {
        Self {
            gdb: false,
            debug: false,
            cmd,
            copy_files: probe_headers::CopyFiles::Lazily,
        }
    }

    /// Set if the process should be run under gdb, implies debug.
    pub fn gdb(mut self, gdb: bool) -> Self {
        self.gdb = gdb;
        self
    }

    /// Set if the debug version of libprobe should be used.
    pub fn debug(mut self, debug: bool) -> Self {
        self.debug = debug;
        self
    }

    pub fn copy_files(mut self, copy_files: probe_headers::CopyFiles) -> Self {
        self.copy_files = copy_files;
        self
    }
}

fn concat_osstrings<const SIZE: usize>(strings: [OsString; SIZE]) -> OsString {
    let mut result = OsString::new();
    for s in strings {
        result.push(s);
    }
    result
}
