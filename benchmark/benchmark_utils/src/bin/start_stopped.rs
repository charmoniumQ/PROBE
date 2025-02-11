use benchmark_utils::util;
use clap::Parser;
use stacked_errors::{Error, StackableErr};

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Start a process in stopped state. Send SIGCONT to resume."
)]
struct Command {
    #[arg(long)]
    verbose: bool,

    /// Executable to run with resource limits
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        let command = Command::parse();
        if command.verbose {
            eprintln!("Issuing SIGSTP");
        }
        nix::sys::signal::raise(nix::sys::signal::Signal::SIGTSTP)
            .map_err(Error::from_err)
            .stack()?;
        if command.verbose {
            eprintln!("Resumed");
        }

        let mut cmd = std::process::Command::new(&command.cmd[0]);
        cmd.args(&command.cmd[1..]);
        if command.verbose {
            eprintln!("+ {command:?}");
        }
        cmd.status().map_err(Error::from_err).stack()
    })
}
