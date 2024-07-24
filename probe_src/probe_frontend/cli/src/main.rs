use std::{ffi::OsString, fs::File};

use clap::{arg, command, value_parser, Command};
use color_eyre::eyre::{eyre, Context, Result};
use flate2::Compression;

/// Output the ops from a probe log file to stdout.
mod dump;

/// Run commands under provenance and generate probe record directory.
mod record;

/// Wrapper over [`probe_frontend::transcribe`].
mod transcribe;

/// Utility code for creating temporary directories.
mod util;

fn main() -> Result<()> {
    color_eyre::install()?;
    env_logger::Builder::from_env(env_logger::Env::new().filter_or("__PROBE_LOG", "warn")).init();
    log::debug!("Logger initialized");

    let matches = command!()
        .about("Generate or manipulate Provenance for Replay OBservation Engine (PROBE) logs.")
        .propagate_version(true)
        .subcommands([
            Command::new("record")
                .args([
                    arg!(-o --output <PATH> "Set destinaton for recording.")
                        .required(false)
                        .value_parser(value_parser!(OsString)),
                    arg!(-f --overwrite "Overwrite existing output if it exists.")
                        .required(false)
                        .value_parser(value_parser!(bool)),
                    arg!(-n --"no-transcribe" "Emit PROBE record rather than PROBE log.")
                        .required(false)
                        .value_parser(value_parser!(bool)),
                    arg!(--gdb "Run under gdb.")
                        .required(false)
                        .value_parser(value_parser!(bool)),
                    arg!(--debug "Run in verbose & debug build of libprobe.")
                        .required(false)
                        .value_parser(value_parser!(bool)),
                    arg!(<CMD> ... "Command to execute under provenance.")
                        .required(true)
                        .trailing_var_arg(true)
                        .value_parser(value_parser!(OsString)),
                ])
                .about("Execute a command and record its provenance"),
            Command::new("transcribe")
                .args([
                    arg!(-f --overwrite "Overwrite existing output if it exists.")
                        .required(false)
                        .value_parser(value_parser!(bool)),
                    arg!(-o --output <PATH> "Path to write the transcribed PROBE log.")
                        .required(false)
                        .default_value("probe_log")
                        .value_parser(value_parser!(OsString)),
                    arg!(-i --input <PATH> "Path to read the PROBE record from.")
                        .required(false)
                        .default_value("probe_record")
                        .value_parser(value_parser!(OsString)),
                ])
                .about("Convert PROBE records to PROBE logs."),
            Command::new("dump")
                .args([
                    arg!(--json "Output JSON.")
                        .required(false)
                        .value_parser(value_parser!(bool)),
                    arg!(-i --input <PATH> "Path to load PROBE log from.")
                        .required(false)
                        .default_value("probe_log")
                        .value_parser(value_parser!(OsString)),
                ])
                .about("Write the data from probe log data in a human-readable manner"),
            Command::new("__gdb-exec-shim").hide(true).arg(
                arg!(<CMD> ... "Command to run")
                    .required(true)
                    .trailing_var_arg(true)
                    .value_parser(value_parser!(OsString)),
            ),
        ])
        .get_matches();

    match matches.subcommand() {
        Some(("record", sub)) => {
            let output = sub.get_one::<OsString>("output").cloned();
            let overwrite = sub.get_flag("overwrite");
            let no_transcribe = sub.get_flag("no-transcribe");
            let gdb = sub.get_flag("gdb");
            let debug = sub.get_flag("debug");
            let cmd = sub
                .get_many::<OsString>("CMD")
                .unwrap()
                .cloned()
                .collect::<Vec<_>>();

            if no_transcribe {
                record::record_no_transcribe(output, overwrite, gdb, debug, cmd)
            } else {
                record::record_transcribe(output, overwrite, gdb, debug, cmd)
            }
            .wrap_err("Record command failed")
        }
        Some(("transcribe", sub)) => {
            let overwrite = sub.get_flag("overwrite");
            let output = sub.get_one::<OsString>("output").unwrap().clone();
            let input = sub.get_one::<OsString>("input").unwrap().clone();

            if overwrite {
                File::create(&output)
            } else {
                File::create_new(&output)
            }
            .wrap_err("Failed to create output file")
            .map(|file| {
                tar::Builder::new(flate2::write::GzEncoder::new(file, Compression::default()))
            })
            .and_then(|mut tar| transcribe::transcribe(input, &mut tar))
            .wrap_err("Transcribe command failed")
        }
        Some(("dump", sub)) => {
            let json = sub.get_flag("json");
            let input = sub.get_one::<OsString>("input").unwrap().clone();

            if json {
                dump::to_stdout_json(input)
            } else {
                dump::to_stdout(input)
            }
            .wrap_err("Dump command failed")
        }
        Some(("__gdb-exec-shim", sub)) => {
            let cmd = sub
                .get_many::<OsString>("CMD")
                .unwrap()
                .cloned()
                .collect::<Vec<_>>();

            let e = exec::Command::new(&cmd[0]).args(&cmd[1..]).exec();

            Err(e).wrap_err("Shim failed to exec")
        }
        None => Err(eyre!("Subcommand expected, try --help for more info")),
        _ => Err(eyre!("Unknown subcommand")),
    }
}
