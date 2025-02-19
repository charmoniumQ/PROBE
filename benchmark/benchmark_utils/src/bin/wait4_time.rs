use clap::Parser;
use serde::Serialize;
use wait4::Wait4;

#[derive(Parser, Debug)]
#[command(version = "0.1.0", about = "Times the given command using wait4")]
struct Command {
    /// Path to write resource utilization to
    #[arg(long, default_value = "time.json")]
    output: std::path::PathBuf,

    /// Executable to time
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

#[derive(Serialize)]
pub struct Rusage {
    cpu_user_us: u128,
    cpu_system_us: u128,
    peak_memory_usage: u64,
    walltime_us: u128,
    returncode: i32,
    signal: i32,
}

fn main() -> std::process::ExitCode {
    use benchmark_utils::util;
    use stacked_errors::{anyhow, Error, StackableErr};
    use std::os::unix::process::ExitStatusExt;
    util::replace_err_with(244, || {
        let command = Command::parse();

        let mut run_cmd = std::process::Command::new(&command.cmd[0]);
        run_cmd.args(&command.cmd[1..]);

        let start = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(Error::from_err)
            .stack()?
            .as_micros();

        let ret = run_cmd
            .spawn()
            .map_err(Error::from_err)
            .context(anyhow!("Error launching {:?}", run_cmd))
            .stack()?
            .wait4()
            .context(anyhow!("Error launching {:?}", run_cmd))
            .stack()?;

        let stop = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(Error::from_err)
            .stack()?
            .as_micros();

        let file = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(&command.output)
            .context(anyhow!("{:?}", command.output))
            .stack()?;

        let usage = Rusage {
            cpu_user_us: ret.rusage.utime.as_micros(),
            cpu_system_us: ret.rusage.stime.as_micros(),
            peak_memory_usage: ret.rusage.maxrss,
            walltime_us: stop - start,
            returncode: ret.status.code().unwrap_or(127),
            signal: ret.status.signal().unwrap_or(0),
        };

        serde_json::to_writer(file, &usage).stack()?;

        Ok(ret.status)
    })
}
