use std::{
    ffi::OsString,
    fs::{self, File},
    os::unix::process::ExitStatusExt,
    path::{Path, PathBuf},
    thread,
};

use color_eyre::eyre::{eyre, Result, WrapErr};
use flate2::Compression;

use crate::{transcribe, util::Dir};

// TODO: modularize and improve ergonomics (maybe expand builder pattern?)

/// create a probe record directory from command arguments
pub fn record_no_transcribe(
    output: Option<OsString>,
    overwrite: bool,
    gdb: bool,
    debug: bool,
    copy_files: bool,
    cmd: Vec<OsString>,
) -> Result<()> {
    let output = match output {
        Some(x) => fs::canonicalize(x).wrap_err("Failed to canonicalize record directory path")?,
        None => {
            let mut output = std::env::current_dir().wrap_err("Failed to get CWD")?;
            output.push("probe_record");
            output
        }
    };

    if overwrite {
        if let Err(e) = fs::remove_dir_all(&output) {
            match e.kind() {
                std::io::ErrorKind::NotFound => (),
                _ => return Err(e).wrap_err("Failed to remove exisitng record directory"),
            }
        }
    }

    let record_dir = Dir::new(output).wrap_err("Failed to create record directory")?;

    Recorder::new(cmd, record_dir)
        .gdb(gdb)
        .debug(debug)
        .copy_files(copy_files)
        .record()?;

    Ok(())
}

/// create a probe log file from command arguments
pub fn record_transcribe(
    output: Option<OsString>,
    overwrite: bool,
    gdb: bool,
    debug: bool,
    copy_files: bool,
    cmd: Vec<OsString>,
) -> Result<()> {
    let output = match output {
        Some(x) => x,
        None => OsString::from("probe_log"),
    };

    let file = if overwrite {
        File::create(&output)
    } else {
        File::create_new(&output)
    }
    .wrap_err("Failed to create output file")?;

    let mut tar = tar::Builder::new(flate2::write::GzEncoder::new(file, Compression::default()));

    let mut record_dir = Recorder::new(
        cmd,
        Dir::temp(true).wrap_err("Failed to create record directory")?,
    )
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
            record_dir.drop = false;
            return Err(e).wrap_err("Failed to transcirbe record directory");
        }
    };

    Ok(())
}

/// Builder for running processes under provenance.
// TODO: extract this into the library part of this project
#[derive(Debug)]
pub struct Recorder {
    gdb: bool,
    debug: bool,
    copy_files: bool,

    output: Dir,
    cmd: Vec<OsString>,
}

impl Recorder {
    /// runs the built recorder, on success returns the PID of launched process and the TempDir it
    /// was recorded into
    pub fn record(self) -> Result<Dir> {
        // reading and canonicalizing path to libprobe
        let mut libprobe = fs::canonicalize(match std::env::var_os("__PROBE_LIB") {
            Some(x) => PathBuf::from(x),
            None => return Err(eyre!("couldn't find libprobe, are you using the wrapper?")),
        })
        .wrap_err("unable to canonicalize libprobe path")?;
        if self.debug || self.gdb {
            log::debug!("Using debug version of libprobe");
            libprobe.push("libprobe-dbg.so");
        } else {
            libprobe.push("libprobe.so");
        }

        // append any existing LD_PRELOAD overrides; libprobe needs to be explicitly converted from
        // a PathBuf to a OsString because PathBuf::push() automatically adds path separators which
        // is incorrect here.
        let mut ld_preload = OsString::from(libprobe);
        if let Some(x) = std::env::var_os("LD_PRELOAD") {
            ld_preload.push(":");
            ld_preload.push(&x);
        }

        let mut child = if self.gdb {
            let mut dir_env = OsString::from("--init-eval-command=set environment __PROBE_DIR=");
            dir_env.push(self.output.path());
            let mut preload_env = OsString::from("--init-eval-command=set environment LD_PRELOAD=");
            preload_env.push(ld_preload);

            let self_bin =
                std::env::current_exe().wrap_err("Failed to get path to current executable")?;

            std::process::Command::new("gdb")
                .arg(dir_env)
                .arg(preload_env)
                .arg("--args")
                .arg(self_bin)
                .arg("__gdb-exec-shim")
                .args(if self.copy_files {
                    std::vec!["--copy-files"]
                } else {
                    std::vec![]
                })
                .args(&self.cmd)
                .env_remove("__PROBE_LIB")
                .env_remove("__PROBE_LOG")
                .spawn()
                .wrap_err("Failed to launch gdb")?
        } else {
            /* We start `env $cmd` instead of `$cmd`
             * This is because PROBE is not able to capture the arguments of the very first process, but it does capture the arguments of any subsequent exec(...).
             * Therefore, the "root process" is env, and the user's $cmd is exec(...)-ed.
             * We could change this by adding argv and environ to InitProcessOp, but I think this solution is more elegant.
             * Since the root process has special quirks, it should not be user's `$cmd`.
             * */
            std::process::Command::new("env")
                .args(self.cmd)
                .env_remove("__PROBE_LIB")
                .env_remove("__PROBE_LOG")
                .env("__PROBE_COPY_FILES", if self.copy_files { "1" } else { "" })
                .env("__PROBE_DIR", self.output.path())
                .env("LD_PRELOAD", ld_preload)
                .spawn()
                .wrap_err("Failed to launch child process")?
        };

        if !self.gdb {
            // without this the child process typically won't have written it's first op by the
            // time we do our sanity check, since we're about to wait on child anyway, this isn't a
            // big deal.
            thread::sleep(std::time::Duration::from_millis(50));

            match Path::read_dir(self.output.path()) {
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

        Ok(self.output)
    }

    /// Create new [`Recorder`] from a command and the directory where it should write the probe
    /// record.
    ///
    /// `cmd[0]` will be used as the command while `cmd[1..]` will be used as the arguments.
    pub fn new(cmd: Vec<OsString>, output: Dir) -> Self {
        Self {
            gdb: false,
            debug: false,
            copy_files: false,
            output,
            cmd,
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

    /// Set if probe should copy files needed to re-execute.
    pub fn copy_files(mut self, copy_files: bool) -> Self {
        self.copy_files = copy_files;
        self
    }
}
