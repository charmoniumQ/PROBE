use clap::{arg, command, value_parser, Command};
use color_eyre::eyre::{eyre, Context, Result};
use flate2::Compression;
use std::{
    ffi::OsString,
    fs::File,
    os::unix::process::ExitStatusExt,
    process::{ExitCode, ExitStatus},
};

/// Run commands under provenance and generate probe record directory.
mod record;

/// Wrapper over [`probe_lib::transcribe`].
mod transcribe;

/// Utility code for creating temporary directories.
mod util;

fn inner_main() -> Result<ExitStatus> {
    color_eyre::install()?;
    env_logger::Builder::from_env(env_logger::Env::new().filter_or("PROBE_LOG", "warn")).init();
    log::debug!("Logger initialized");

    let matches = command!()
        .about("Generate or manipulate Provenance for Replay OBservation Engine (PROBE) logs.")
        .propagate_version(true)
        .allow_external_subcommands(true)
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
                    arg!(-e --"copy-files-eagerly" "Eagerly copy files that would be needed to re-execute the program.")
                        .required(false)
                        .value_parser(value_parser!(bool)),
                    arg!(-c --"copy-files-lazily" "lazily Copy files that would be needed to re-execute the program.")
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
            Command::new("__exec").hide(true).arg(
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
            let copy_files_eagerly = sub.get_flag("copy-files-eagerly");
            let copy_files_lazily = sub.get_flag("copy-files-lazily");
            let cmd = sub
                .get_many::<OsString>("CMD")
                .unwrap()
                .cloned()
                .collect::<Vec<_>>();

            if copy_files_eagerly && copy_files_lazily {
                Err(eyre!(
                    "Cannot copy files both eagerly and lazily; please discard one or both"
                ))
            } else {
                if no_transcribe {
                    record::record_no_transcribe(
                        output,
                        overwrite,
                        gdb,
                        debug,
                        copy_files_eagerly,
                        copy_files_lazily,
                        cmd,
                    )
                } else {
                    record::record_transcribe(
                        output,
                        overwrite,
                        gdb,
                        debug,
                        copy_files_eagerly,
                        copy_files_lazily,
                        cmd,
                    )
                }
                .wrap_err("Record command failed")
            }
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
            .wrap_err("Transcribe command failed")?;

            Ok(ExitStatus::from_raw(0))
        }
        Some(("__exec", sub)) => {
            let cmd = sub
                .get_many::<OsString>("CMD")
                .unwrap()
                .cloned()
                .collect::<Vec<_>>();

            let e = exec::Command::new(&cmd[0]).args(&cmd[1..]).exec();

            Err(e).wrap_err("Shim failed to exec")
        }
        Some((subcommand, args)) => {
            let args = args
                .get_many::<OsString>("")
                .unwrap()
                .cloned()
                .collect::<Vec<_>>();

            std::process::Command::new("python3")
                .arg("-m")
                .arg("probe_py.cli")
                .arg(subcommand)
                .args(&args)
                .spawn()
                .wrap_err("Unknown subcommand")?
                .wait()
                .wrap_err("Wait on subcommand failed")
        }
        None => Err(eyre!("Subcommand expected, try --help for more info")),
    }
}

const PROBE_EXIT_BAD_CHILD_CODE: u8 = 57;
const PROBE_EXIT_TERM_BY_SIGNAL: u8 = 58;
const PROBE_EXIT_PRINTED_ERROR: u8 = 58;

fn main() -> ExitCode {
    match inner_main() {
        Ok(exit_status) => {
            if exit_status.success() {
                ExitCode::SUCCESS
            } else {
                match exit_status.code() {
                    Some(exit_status_code) => ExitCode::from(
                        u8::try_from(exit_status_code).unwrap_or(PROBE_EXIT_BAD_CHILD_CODE),
                    ),
                    None => ExitCode::from(PROBE_EXIT_TERM_BY_SIGNAL),
                }
            }
        }
        Err(err) => {
            eprintln!("{:?}", err);
            ExitCode::from(PROBE_EXIT_PRINTED_ERROR)
        }
    }
}
