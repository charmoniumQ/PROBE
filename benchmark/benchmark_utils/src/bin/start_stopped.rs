use benchmark_utils::util;
use clap::Parser;
use stacked_errors::{Error, StackableErr};

#[derive(Parser, Debug)]
#[command(version = "0.1.0", about = "Start a process in stopped state")]
struct Command {
    /// Executable to run with resource limits
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        nix::sys::signal::raise(nix::sys::signal::Signal::SIGTSTP)
            .map_err(Error::from_err)
            .stack()?;

        let command = Command::parse();

        let mut cmd = std::process::Command::new(&command.cmd[0]);
        cmd.args(&command.cmd[1..]);
        cmd.status().map_err(Error::from_err).stack()
    })
}
