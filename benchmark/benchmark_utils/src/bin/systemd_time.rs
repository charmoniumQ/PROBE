use clap::Parser;
use stacked_errors::{anyhow, Result, StackableErr};

use benchmark_utils::cgroups;
use benchmark_utils::privs;
use benchmark_utils::util;

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Times the given command using the current cgroup"
)]
struct Command {
    /// Path to write resource utilization to
    #[arg(long)]
    output: String,

    /// Executable to time
    #[arg()]
    exe: std::path::PathBuf,

    /// Command to run in the benchmark sandbox
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    args: Vec<String>,
}

fn main() -> Result<()> {
    privs::initially_reduce_privileges();

    let current_cgroup = cgroups::Cgroup::current().stack()?;

    let command = Command::parse();

    privs::with_escalated_privileges(|| current_cgroup.reset_counters().stack())?;

    let pre_rusage = current_cgroup.get_rusage().stack()?;

    let mut run_benchmark = std::process::Command::new(command.exe);
    run_benchmark.args(command.args);
    let ret = util::check_cmd(run_benchmark, false).stack();

    let usage = current_cgroup.get_rusage().stack()? - pre_rusage;

    let file = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(command.output.clone())
        .context(anyhow!("{:?}", command.output))
        .stack()?;
    serde_yaml::to_writer(file, &usage).stack()?;

    ret
}
