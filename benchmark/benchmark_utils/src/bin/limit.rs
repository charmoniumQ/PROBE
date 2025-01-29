use clap::Parser;
use stacked_errors::{anyhow, Error, Result, StackableErr};

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Limits total CPU time and memory usage of a process",
    long_about = "
This is separated from stabalize because stabalize requires setuid and this does not.
"
)]
struct Command {
    /// Soft limit on CPU seconds.
    #[arg(long)]
    cpu_seconds: Option<u64>,

    /// Limit on consumable memory
    #[arg(long)]
    mem_bytes: Option<u64>,

    /// Command to run in the benchmark sandbox
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> Result<()> {
    let command = Command::parse();
    apply_limits(command.cpu_seconds, command.mem_bytes)?;

    let exe = command.cmd[0].clone();
    let args = command.cmd[1..].into_iter().collect::<std::vec::Vec<_>>();
    let mut cmd = std::process::Command::new(exe);
    cmd.args(args);

    let ret = cmd
        .status()
        .context(anyhow!("Executing cmd {:?}", cmd))
        .stack()?;

    if ret.success() {
        Ok(())
    } else {
        Err(anyhow!("{:?} failed with {:?}", cmd, ret))
    }
}

fn apply_limits(cpu_seconds: Option<u64>, mem_bytes: Option<u64>) -> Result<()> {
    if let Some(real_cpu_seconds) = cpu_seconds {
        rlimit::Resource::CPU
            .set(real_cpu_seconds, real_cpu_seconds + real_cpu_seconds / 10)
            .map_err(Error::from_err)?
    }
    if let Some(real_mem_bytes) = mem_bytes {
        rlimit::Resource::AS
            .set(real_mem_bytes, real_mem_bytes)
            .map_err(Error::from_err)?;
    }
    Ok(())
}
