use std::{
    ffi::{OsStr, OsString},
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
};

use clap::Parser;
use color_eyre::eyre::{eyre, Context, Report, Result};
use flate2::Compression;

mod arena;
mod display;
mod ffi;
mod metadata;
mod ops;

#[derive(clap::Parser, Debug, Clone)]
#[command(author, version, about, long_about = None)]
#[command(propagate_version = true)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(clap::Subcommand, Debug, Clone)]
enum Command {
    /// Execute a command and record its provenance
    Record {
        /// Directory to output PROBE log to
        #[arg(short, long, required = false, default_value = "probe_log")]
        output: OsString,

        /// Overwrite existing output directory if it exists
        #[arg(short = 'f', long)]
        overwrite: bool,

        /// Run in gdb
        #[arg(long)]
        gdb: bool,

        /// Override the path to libprobe.so (this path will be canonicalized)
        #[arg(long)]
        lib_path: Option<PathBuf>,

        /// Run in verbose & debug build of libprobe
        #[arg(long)]
        debug: bool,

        /// Command to execute under provenance
        #[arg(required = true)]
        cmd: Vec<OsString>,
    },

    /// Write the data from probe log data in a human-readable manner
    Dump {
        /// Directory to load PROBE log from
        #[arg(short, long, required = false, default_value = "probe_log")]
        input: OsString,
    },
}

fn main() -> Result<()> {
    color_eyre::install()?;

    match Cli::parse().command {
        Command::Record {
            output,
            overwrite,
            gdb,
            lib_path,
            debug,
            cmd,
        } => {
            if PathBuf::from(output.clone()).exists() && overwrite {
                fs::remove_file(&output).wrap_err("Error deleting old output file")?;
            }

            let mut ld_preload = fs::canonicalize(match lib_path {
                Some(x) => x,
                None => match std::env::var_os("__PROBE_LIB") {
                    Some(x) => PathBuf::from(x),
                    None => match Path::new("/usr/share/probe").exists() {
                        true => PathBuf::from("/usr/share/probe"),
                        false => {
                            return Err(eyre!(
                                "Can't find libprobe lib path, ensure libprobe is installed in \
                                /usr/share/probe or set --lib-path or __PROBE_LIB"
                            ))
                        }
                    },
                },
            })
            .wrap_err("unable to canonicalize lib path")?;

            if debug || gdb {
                ld_preload.push("libprobe-dbg.so");
            } else {
                ld_preload.push("libprobe.so");
            }

            if let Some(x) = std::env::var_os("LD_PRELOAD") {
                ld_preload.push(":");
                ld_preload.push(&x);
            }

            let dir = tempfile::tempdir().wrap_err("Failed to create arena directory")?;

            let mut popen = if gdb {
                let mut dir_env = OsString::from("__PROBE_DIR=");
                dir_env.push(dir.path());
                let mut preload_env = OsString::from("LD_PRELOAD=");
                preload_env.push(ld_preload);

                subprocess::Exec::cmd("gdb")
                    .args(&[
                        OsStr::new("--args"),
                        OsStr::new("env"),
                        &dir_env,
                        &preload_env,
                    ])
                    .args(&cmd)
            } else {
                subprocess::Exec::cmd(&cmd[0])
                    .args(&cmd[1..])
                    .env("LD_PRELOAD", ld_preload)
                    .env("__PROBE_DIR", dir.path())
            }
            .popen()
            .wrap_err("Failed to launch process")?;

            let metadata = metadata::Metadata::new(
                popen
                    .pid()
                    .expect("just popened process should always have PID") as i32,
            );

            popen.wait().wrap_err("Error awaiting child process")?;

            let file = match File::create_new(output) {
                Ok(x) => x,
                Err(e) => {
                    log::error!("Failed to create output file: {}", e);

                    let path = format!(
                        "probe_log_{}_{}",
                        std::process::id(),
                        std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .wrap_err("current system time before unix epoch")?
                            .as_secs()
                    );

                    let tmp =
                        File::create_new(&path).wrap_err("Failed to create backup output file");

                    log::error!("backup output file '{}' will be used instead", &path);

                    tmp
                }
                .wrap_err("Failed to create output dir")?,
            };

            let mut tar =
                tar::Builder::new(flate2::write::GzEncoder::new(file, Compression::default()));

            let outdir = tempfile::tempdir()?;

            File::create_new(outdir.path().join("_metadata"))
                .wrap_err("failed to create metadata file in output directory")?
                .write_all(
                    serde_json::to_string(&metadata)
                        .wrap_err("Error serializng metadata")?
                        .as_bytes(),
                )
                .wrap_err("Error writing metadata")?;

            arena::parse_arena_dir(dir.path(), &outdir)
                .wrap_err("Unable to decode arena directory")?;

            tar.append_dir_all(".", &outdir)
                .wrap_err("Failed to copy output dir into archive")?;
            tar.finish().wrap_err("Failed to finish writing tarball")?;

            if let Err(e) = outdir.close() {
                log::warn!("Failed to close output directory: {}", e);
            }

            if let Err(e) = dir.close() {
                log::warn!("Failed to close arena directory: {}", e);
            }

            Ok::<(), Report>(())
        }
        .wrap_err("Record command failed"),
        Command::Dump { input } => {
            let file = flate2::read::GzDecoder::new(File::open(&input).wrap_err(format!(
                "Failed to open input file '{}'",
                input.to_string_lossy()
            ))?);

            let mut tar = tar::Archive::new(file);

            tar.entries()
                .wrap_err("Unable to get tarball entry iterator")?
                .try_for_each(|x| {
                    let mut entry = x.wrap_err("Unable to extract tarball entry")?;

                    let path = entry
                        .path()
                        .wrap_err("Error getting path of tarball entry")?
                        .as_ref()
                        .to_str()
                        .ok_or_else(|| eyre!("Tarball entry path not valid UTF-8"))?
                        .to_owned();

                    if path == "_metadata" {
                        return Ok(());
                    }

                    let mut buf = String::new();
                    let size = entry
                        .read_to_string(&mut buf)
                        .wrap_err("unable to read contents of tarball entry")?;

                    // this is the case where the entry is a directory
                    if size == 0 {
                        return Ok(());
                    }

                    let hierarchy = path
                        .split('/')
                        .map(|x| {
                            x.parse::<usize>().wrap_err(format!(
                                "Unable to convert path component '{x}' to integer"
                            ))
                        })
                        .collect::<Result<Vec<_>, _>>()
                        .wrap_err("Unable to extract PID.EPOCH.TID hierarchy")?;

                    if hierarchy.len() != 3 {
                        return Err(eyre!("malformed PID.EPOCH.TID hierarchy"));
                    }

                    let ops = buf
                        .split('\n')
                        .filter_map(|x| {
                            if x.is_empty() {
                                return None;
                            }
                            Some(
                                serde_json::from_str::<ops::Op>(x)
                                    .wrap_err("Error deserializing Op"),
                            )
                        })
                        .collect::<Result<Vec<_>, _>>()
                        .wrap_err("Failed to deserialize TID file")?;

                    let mut stdout = std::io::stdout().lock();
                    for op in ops {
                        writeln!(
                            stdout,
                            "{}.{}.{} >>> {}",
                            hierarchy[0], hierarchy[1], hierarchy[2], op,
                        )
                        .wrap_err("Error printing Op")?;
                    }

                    Ok(())
                })
        }
        .wrap_err("Dump command failed"),
    }
}
