use std::{
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    thread,
};

use color_eyre::eyre::{eyre, Result, WrapErr};

use crate::util::Dir;

#[derive(Debug)]
pub struct Recorder {
    gdb: bool,
    debug: bool,

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

        // append any existing LD_PRELOAD overrides
        let mut ld_preload = OsString::from(libprobe);
        if let Some(x) = std::env::var_os("LD_PRELOAD") {
            ld_preload.push(":");
            ld_preload.push(&x);
        }

        let mut child = if self.gdb {
            let mut dir_env = OsString::from("__PROBE_DIR=");
            dir_env.push(self.output.path());
            let mut preload_env = OsString::from("LD_PRELOAD=");
            preload_env.push(ld_preload);

            std::process::Command::new("gdb")
                .arg("--args")
                .arg("env")
                .arg(dir_env)
                .arg(preload_env)
                .args(&self.cmd)
                .env_remove("__PROBE_LIB")
                .env_remove("__PROBE_LOG")
                .spawn()
                .wrap_err("Failed to launch gdb")?
        } else {
            std::process::Command::new(&self.cmd[0])
                .args(&self.cmd[1..])
                .env_remove("__PROBE_LIB")
                .env_remove("__PROBE_LOG")
                .env("__PROBE_DIR", self.output.path())
                .env("LD_PRELOAD", ld_preload)
                .spawn()
                .wrap_err("Failed to launch child process")?
        };

        thread::sleep(std::time::Duration::from_millis(50));

        match Path::read_dir(self.output.path()) {
            Ok(x) => {
                let any_files = x
                    .into_iter()
                    .try_fold(false, |_, x| x.map(|x| x.path().exists()))?;
                if !any_files {
                    log::warn!(
                        "No arean files detected, something is wrong, you should probably abort!"
                    );
                }
            }
            Err(e) => {
                return Err(e)
                    .wrap_err("Unable to read record directory during post-startup sanity check")
            }
        }

        child.wait().wrap_err("Failed to await child process")?;

        Ok(self.output)
    }
    pub fn new(cmd: Vec<OsString>, output: Dir) -> Self {
        Self {
            gdb: false,
            debug: false,

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
}
