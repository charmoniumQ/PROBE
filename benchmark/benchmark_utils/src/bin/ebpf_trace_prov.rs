use benchmark_utils::{privs, util};
use clap::Parser;
use stacked_errors::{anyhow, bail, Error, StackableErr};

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Temporarily installs eBPF tracers to trace command"
)]
struct Command {
    /// Soft limit on CPU seconds.
    #[arg(long)]
    log_file: std::path::PathBuf,

    /// Executable to run with resource limits
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        privs::initially_reduce_privileges().stack()?;

        let start_stopped = std::env::current_exe()
            .map_err(Error::from_err)
            .stack()?
            .parent()
            .ok_or(anyhow!("Current exe has no parent"))
            .stack()?
            .join("target/debug/start_stopped");
        if !start_stopped.exists() {
            bail!("{start_stopped:?} does not exist. Please run `cargo build`");
        }

        let bpftrace = std::path::PathBuf::from(NIX_BPFTRACE_PATH.to_owned()).join("bin/bpftrace");
        privs::verify_safe_to_run_as_root(&bpftrace).stack()?;

        let command = Command::parse();

        let mut cmd = std::process::Command::new(start_stopped);
        cmd.args(&command.cmd);
        let mut cmd_proc = cmd.spawn().map_err(Error::from_err).stack()?;

        let tmp_dir = tempdir::TempDir::new("ebpf_trace_prov")
            .map_err(Error::from_err)
            .stack()?;

        util::write_to_file_truncate(&command.log_file, "").stack()?;

        let bpftrace_proc = privs::with_escalated_privileges(|| {
            let bpftrace_file = tmp_dir.path().to_owned().join("log");

            util::write_to_file_truncate(&bpftrace_file, BPFTRACE_SOURCE).stack()?;

            let mut bpftrace_cmd = std::process::Command::new(bpftrace);
            bpftrace_cmd.args([
                "-B".into(),
                "full".into(),
                "-f".into(),
                "json".into(),
                "-o".into(),
                Into::<std::ffi::OsString>::into(&command.log_file),
                Into::<std::ffi::OsString>::into(&bpftrace_file),
                (&cmd_proc.id().to_string()).into(),
            ]);
            let bpftrace_proc = bpftrace_cmd.spawn().map_err(Error::from_err).stack()?;

            while std::fs::read_to_string(&command.log_file)
                .map_err(Error::from_err)
                .stack()?
                .contains("launch_pid")
            {
                nix::sched::sched_yield().map_err(Error::from_err).stack()?;
            }

            Ok(bpftrace_proc)
        })
        .stack()?;

        #[allow(clippy::cast_possible_wrap)]
        let signed_pid = cmd_proc.id() as i32;
        while !std::fs::read_to_string(format!("/proc/{signed_pid}/wchan"))
            .map_err(Error::from_err)
            .stack()?
            .starts_with("do_signal_stop") {
                nix::sched::sched_yield().map_err(Error::from_err).stack()?;
            }
        nix::sys::signal::kill(
            nix::unistd::Pid::from_raw(signed_pid),
            nix::sys::signal::Signal::SIGCONT,
        )
        .map_err(Error::from_err)
        .stack()?;

        let cmd_status = cmd_proc.wait().map_err(Error::from_err).stack();

        privs::with_escalated_privileges(|| {
            #[allow(clippy::cast_possible_wrap)]
            let signed_pid = bpftrace_proc.id() as i32;
            nix::sys::signal::kill(
                nix::unistd::Pid::from_raw(signed_pid),
                nix::sys::signal::Signal::SIGTERM,
            )
            .map_err(Error::from_err)
            .stack()?;
            Ok(())
        })
        .stack()?;

        privs::permanently_drop_privileges().stack()?;

        cmd_status
    })
}

const NIX_BPFTRACE_PATH: &str = env!("NIX_BPFTRACE_PATH");
const BPFTRACE_SOURCE: &str = include_str!("../../bpftrace_prov.bt");
