use benchmark_utils::cgroups;
use benchmark_utils::util;
use clap::Parser;
use stacked_errors::{anyhow, Error, StackableErr};

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Times the given command using the current cgroup",
    long_about = "If your system does not have cgroupsv2, consider using getrusage (Crate Nix)."
)]
struct Command {
    /// Path to write resource utilization to
    #[arg(long, default_value = "time.json")]
    output: std::path::PathBuf,

    /// Executable to time
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        let current_cgroup = cgroups::Cgroup::current().stack()?;

        let command = Command::parse();

        let pre_rusage = current_cgroup.get_rusage(None).stack()?;

        let mut run_cmd = std::process::Command::new(&command.cmd[0]);
        run_cmd.args(&command.cmd[1..]);
        let ret = run_cmd
            .status()
            .map_err(Error::from_err)
            .context(anyhow!("Error launching {:?}", run_cmd))
            .stack()?;

        let usage = current_cgroup.get_rusage(Some(ret)).stack()? - pre_rusage;

        let file = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(&command.output)
            .context(anyhow!("{:?}", command.output))
            .stack()?;

        serde_json::to_writer(file, &usage).stack()?;

        Ok(ret)
    })
}
