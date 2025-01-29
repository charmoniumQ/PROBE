use clap::Parser;
use itertools::Itertools;
use stacked_errors::{anyhow, Error, Result, StackableErr};
use std::collections::btree_set::BTreeSet;
use std::path::PathBuf;

use benchmark_utils::privs;
use benchmark_utils::sys_config;
use benchmark_utils::util;

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Steps to stabalize the benchmarking of the given command",
    long_about = "

"
)]
struct Command {
    /// CPUs to reserve
    #[arg(long, value_delimiter = ',')]
    cpus: Vec<sys_config::Cpu>,

    #[arg(long, default_value_t = false)]
    enable_internet: bool,

    /// Soft limit on CPU seconds.
    #[arg(long)]
    cpu_seconds: Option<u64>,

    /// Limit on consumable memory
    #[arg(long)]
    mem_bytes: Option<u64>,

    /// Limit on consumable swap memory
    #[arg(long)]
    swap_mem_bytes: Option<u64>,

    #[arg(long)]
    nice: Option<i8>,

    /// Priority (aka niceness), also used for IO priority
    #[arg(long)]
    prio: Option<i32>,

    /// Executable to launch
    exe: PathBuf,

    /// Arguments for executable
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    args: Vec<String>,
}

fn main() -> Result<()> {
    privs::initially_reduce_privileges();

    let systemctl_path = PathBuf::from(SYSTEMCTL_PATH);
    privs::verify_safe_to_run_as_root(&systemctl_path).stack()?;

    let systemd_run_path = PathBuf::from(SYSTEMD_RUN_PATH);
    privs::verify_safe_to_run_as_root(&systemd_run_path).stack()?;

    let command = Command::parse();

    let cpus = BTreeSet::from_iter(command.cpus.into_iter());

    let other_cpus = sys_config::iter_cpus()?
        .into_iter()
        .map(|(cpu, _)| cpu)
        .into_iter()
        .filter(|cpu| !cpus.contains(cpu))
        .collect::<BTreeSet<sys_config::Cpu>>();

    privs::with_escalated_privileges(|| {
        let mut restrict_other_slices = std::process::Command::new(systemctl_path.clone());
        restrict_other_slices.args([
            "set-property",
            "--runtime",
            "*.slice",
            &format!(
                "AllowedCPUs={}",
                other_cpus.into_iter().map(|cpu| cpu.to_string()).join(",")
            ),
        ]);
        util::check_cmd(restrict_other_slices, true).stack()?;

        let mut search_for_benchmarking_slice = std::process::Command::new(systemctl_path.clone());
        search_for_benchmarking_slice.args(["list-unit-files", "benchmarking.slice"]);
        util::check_cmd(search_for_benchmarking_slice, true)
            .stack()
            .or_else(|_| create_systemd_slice())
            .stack()?;

        let mut configure_benchmarking_slice = std::process::Command::new(systemctl_path.clone());
        configure_benchmarking_slice.args([
            "set-property",
            "--runtime",
            "benchmarking.slice",
            &format!(
                "AllowedCPUs={}",
                cpus.into_iter().map(|cpu| cpu.to_string()).join(",")
            ),
            "CPUAccounting=yes",
            "MemoryAccounting=yes",
        ]);
        if let Some(val) = command.mem_bytes {
            configure_benchmarking_slice.arg(&format!("MemoryMax={}", val));
        }
        if let Some(val) = command.swap_mem_bytes {
            configure_benchmarking_slice.arg(&format!("MemorySwapMax={}\n", val));
        }
        if !command.enable_internet {
            // 1. Access is granted when the checked IP address matches an entry in the IPAddressAllow= list.
            // 2. Otherwise, access is denied when the checked IP address matches an entry in the IPAddressDeny= list.
            // 3. Otherwise, access is granted.
            configure_benchmarking_slice.args(["IPAddressAllow=localhost", "IPAddressDeny=any"]);
        }
        util::check_cmd(configure_benchmarking_slice, true).stack()?;

        let mut start_benchmarking_slice = std::process::Command::new(systemctl_path.clone());
        start_benchmarking_slice.args(["start", "benchmark.slice"]);
        start_benchmarking_slice
            .status()
            .map_err(Error::from_err)
            .context(anyhow!("{:?}", start_benchmarking_slice))
            .stack()?;

        let mut run_benchmark = std::process::Command::new(systemd_run_path.clone());
        let resuid = nix::unistd::getresuid().map_err(Error::from_err).stack()?;
        let resgid = nix::unistd::getresgid().map_err(Error::from_err).stack()?;
        let mut chdir_arg = std::ffi::OsString::from("--working-directory=");
        chdir_arg.push(
            std::env::current_dir()
                .map_err(Error::from_err)
                .stack()?
                .into_os_string(),
        );
        run_benchmark.args([
            "--slice=benchmark.slice",
            &format!("--uid={}", resuid.real),
            &format!("--gid={}", resgid.real),
            "--wait",
            "--pipe",
            "--quiet",
        ]);
        run_benchmark.arg(chdir_arg);
        if let Some(value) = command.nice {
            run_benchmark.arg(&format!("--nice={}", value));
        }
        run_benchmark.arg(command.exe);
        run_benchmark.args(command.args);
        let ret = util::check_cmd(run_benchmark, false).stack();

        // let mut stop_slice = std::process::Command::new(systemctl_path.clone());
        // stop_slice.args(["stop", "benchmark.slice"]);
        // util::check_cmd(stop_slice, true).stack()?;

        ret
    })?;

    privs::permanently_drop_privileges();

    Ok(())
}

fn create_systemd_slice() -> Result<()> {
    let slice = format!(
        "
[Unit]
Description=Slice dedicated to benchmarking programs
# https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html
"
    );

    let slice_path = std::path::Path::new("/etc/systemd/system/benchmarking.slice");
    util::write_to_file2(slice_path, slice.to_string())?;

    let systemctl_path = PathBuf::from(SYSTEMCTL_PATH);
    privs::verify_safe_to_run_as_root(&systemctl_path).stack()?;

    let mut systemd_reload = std::process::Command::new(systemctl_path.clone());
    systemd_reload.args(["daemon-reload"]);
    util::check_cmd(systemd_reload, true).stack()
}

const SYSTEMCTL_PATH: &str =
    "/nix/store/3zykdvv4pvs0k11z0bgc96wfjnjjzm4p-systemd-minimal-256.8/bin/systemctl";
const SYSTEMD_RUN_PATH: &str =
    "/nix/store/3zykdvv4pvs0k11z0bgc96wfjnjjzm4p-systemd-minimal-256.8/bin/systemd-run";
