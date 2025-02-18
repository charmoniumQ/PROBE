use benchmark_utils::util;
use clap::Parser;
use stacked_errors::{anyhow, Error, Result, StackableErr};

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Limits total CPU time and memory usage of a process"
)]
struct Command {
    /// Soft limit on CPU seconds.
    #[arg(long)]
    cpu_seconds: Option<u64>,

    /// Limit on consumable memory
    #[arg(long)]
    mem_bytes: Option<u64>,

    /// Executable to run with resource limits
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        let command = Command::parse();

        apply_limits(command.cpu_seconds, command.mem_bytes).stack()?;

        let mut cmd = std::process::Command::new(&command.cmd[0]);
        cmd.args(&command.cmd[1..]);

        cmd.status()
            .context(anyhow!("Executing cmd {:?}", cmd))
            .stack()
    })
}

fn apply_limits(cpu_seconds: Option<u64>, mem_bytes: Option<u64>) -> Result<()> {
    if let Some(real_cpu_seconds) = cpu_seconds {
        nix::sys::resource::setrlimit(
            nix::sys::resource::Resource::RLIMIT_CPU,
            real_cpu_seconds,
            real_cpu_seconds + real_cpu_seconds / 10,
        )
        .map_err(Error::from_err)
        .stack()?;
    }
    if let Some(real_mem_bytes) = mem_bytes {
        nix::sys::resource::setrlimit(
            nix::sys::resource::Resource::RLIMIT_AS,
            real_mem_bytes,
            real_mem_bytes,
        )
        .map_err(Error::from_err)
        .stack()?;
    }
    Ok(())
}
