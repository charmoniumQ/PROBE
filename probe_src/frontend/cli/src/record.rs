use std::{
    ffi::OsString,
    fs::{self, File},
    os::unix::process::ExitStatusExt,
    path::{Path, PathBuf},
    thread,
};

use color_eyre::eyre::{eyre, Result, WrapErr};
use flate2::Compression;
use log::{debug, warn};
use tar::Builder;

use crate::{transcribe, util::Dir};

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

    debug!("Record directory: {:?}", output);

    if overwrite {
        if let Err(e) = fs::remove_dir_all(&output) {
            match e.kind() {
                std::io::ErrorKind::NotFound => (),
                _ => return Err(e).wrap_err("Failed to remove existing record directory"),
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

    debug!("Output file: {:?}", output);

    let file = if overwrite {
        debug!("Overwriting existing file");
        File::create(&output)
    } else {
        debug!("Creating new file");
        File::create_new(&output)
    }
    .wrap_err("Failed to create output file")?;

    let mut tar = Builder::new(flate2::write::GzEncoder::new(file, Compression::default()));

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
            warn!(
                "Error transcribing record directory, saving directory '{}'",
                record_dir.as_ref().to_string_lossy()
            );
            record_dir.drop = false;
            return Err(e).wrap_err("Failed to transcribe record directory");
        }
    };

    Ok(())
}

pub struct Recorder {
    gdb: bool,
    debug: bool,
    copy_files: bool,
    output: Dir,
    cmd: Vec<OsString>,
}

impl Recorder {
    pub fn record(self) -> Result<Dir> {
        let mut libprobe = fs::canonicalize(match std::env::var_os("__PROBE_LIB") {
            Some(x) => PathBuf::from(x),
            None => return Err(eyre!("couldn't find libprobe, are you using the wrapper?")),
        })
        .wrap_err("unable to canonicalize libprobe path")?;

        let lib_extension = if cfg!(target_os = "macos") {
            "dylib"
        } else {
            "so"
        };

        if self.debug || self.gdb {
            debug!("Using debug version of libprobe");
            libprobe.push(format!("libprobe-dbg.{}", lib_extension));
        } else {
            libprobe.push(format!("libprobe.{}", lib_extension));
        }

        let preload_env_var = if cfg!(target_os = "macos") {
            "DYLD_INSERT_LIBRARIES"
        } else {
            "LD_PRELOAD"
        };

        let mut preload_value = OsString::from(libprobe);
        if let Some(x) = std::env::var_os(preload_env_var) {
            preload_value.push(":");
            preload_value.push(&x);
        }

        // Append libinterpose.dylib to DYLD_INSERT_LIBRARIES
        let libinterpose_path = PathBuf::from("/Users/salehamuzammil/Desktop/PROBE/libinterpose.dylib");
        if cfg!(target_os = "macos") {
            preload_value.push(":");
            preload_value.push(libinterpose_path);
        }

        let mut child = if self.gdb {
            let mut dir_env = OsString::from("--init-eval-command=set environment __PROBE_DIR=");
            dir_env.push(self.output.path());
            let mut preload_env = OsString::from("--init-eval-command=set environment ");
            preload_env.push(preload_env_var);
            preload_env.push("=");
            preload_env.push(&preload_value);

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
            std::process::Command::new("env")
                .args(self.cmd)
                .env_remove("__PROBE_LIB")
                .env_remove("__PROBE_LOG")
                .env("__PROBE_COPY_FILES", if self.copy_files { "1" } else { "" })
                .env("__PROBE_DIR", self.output.path())
                .env(preload_env_var, &preload_value)
                .spawn()
                .wrap_err("Failed to launch child process")?
        };

        if !self.gdb {
            thread::sleep(std::time::Duration::from_millis(50));

            match fs::read_dir(self.output.path()) {
                Ok(x) => {
                    let any_files = x
                        .into_iter()
                        .try_fold(false, |_, x| x.map(|x| x.path().exists()))?;
                    if !any_files {
                        warn!(
                            "No arena files detected after 50ms, something is wrong, you should probably abort!"
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

        let exit = child.wait().wrap_err("Failed to await child process")?;
        if !exit.success() {
            match exit.code() {
                Some(code) => warn!("Recorded process exited with code {code}"),
                None => match exit.signal() {
                    Some(sig) => match crate::util::sig_to_name(sig) {
                        Some(name) => warn!("Recorded process exited with signal {name}"),
                        None => {
                            warn!("Recorded process exited with unknown signal {sig}");
                        }
                    },
                    None => warn!("Recorded process exited with unknown error"),
                },
            }
        }

        Ok(self.output)
    }

    pub fn new(cmd: Vec<OsString>, output: Dir) -> Self {
        Self {
            gdb: false,
            debug: false,
            copy_files: false,
            output,
            cmd,
        }
    }

    pub fn gdb(mut self, gdb: bool) -> Self {
        self.gdb = gdb;
        self
    }

    pub fn debug(mut self, debug: bool) -> Self {
        self.debug = debug;
        self
    }

    pub fn copy_files(mut self, copy_files: bool) -> Self {
        self.copy_files = copy_files;
        self
    }
}
