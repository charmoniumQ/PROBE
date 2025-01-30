use clap::Parser;
use stacked_errors::{anyhow, Error, Result, StackableErr};
use std::collections::btree_set::BTreeSet;
use std::path::PathBuf;

use benchmark_utils::privs;
use benchmark_utils::sys_config;
use benchmark_utils::util;

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Shield a CPU from the scheduler and run a process on it.",
    long_about = "

This program does the same task as cpuset/cset (they call it 'shielding'),
except cpuset/cset only works for Cgroups v1. Systemd kind of insists that it is
the only one to directly create cgroupsv2, therefore we go through systemd.

If your system does not have Systemd:

1. If it has Cgroups v2, consider writing cgroupsv2_shield that operates by
   directly manipulating the Cgroups.

2. If it has Cgroups v1, consider writing a setuid wrapper around [cpuset] (see
   [cpuset tutorial]).

3. If it does not have Cgroups or you don't want to use Cgroups, consider
   writing setaffinity_shield that would iterate over all PIDs in the system, and
   call [sched_setaffinity]. sched_setaffinity is how [taskset] works.

4. Lastly, consider benchmarking without CPU shielding. Your results will likely
   contain more variance, but it may be good enough. Consider using bin/limit.rs
   (in this crate) to set the resource limits.

[cpuset]: https://github.com/SUSE/cpuset
[cpuset tutorial]: https://sources.debian.org/data/main/c/cpuset/1.6-4.1/doc/tutorial.html
[sched_setaffinity]: https://www.man7.org/linux/man-pages/man2/sched_setaffinity.2.html
[taskset]: https://www.man7.org/linux/man-pages/man1/taskset.1.html

"
)]
struct Command {
    /// CPUs to reserve
    #[arg(long, value_delimiter = ',')]
    cpus: Vec<sys_config::Cpu>,

    /// Whether to enable access to the external internet
    /// Localhost will still be allowed.
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

    /// Priority (aka niceness) for the process
    #[arg(long)]
    nice: Option<i8>,

    /// Whether to clear or inherit environment variables
    #[arg(long, default_value_t = false)]
    clear_env: bool,

    /// Executable to launch on the shielded CPUs
    exe: String,

    /// Arguments for executable
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    args: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        privs::initially_reduce_privileges().stack()?;

        let systemctl_path = PathBuf::from(SYSTEMCTL_PATH);
        privs::verify_safe_to_run_as_root(&systemctl_path).stack()?;

        let systemd_run_path = PathBuf::from(SYSTEMD_RUN_PATH);
        privs::verify_safe_to_run_as_root(&systemd_run_path).stack()?;

        let command = Command::parse();

        let real_exe = if command.exe.starts_with('/') {
            PathBuf::from(command.exe)
        } else {
            which::which(&command.exe)
                .context(anyhow!(
                    "Could not find {:?} on $PATH {:?}",
                    command.exe,
                    std::env::var("PATH").unwrap_or_default(),
                ))
                .stack()?
        };

        let shielded_cpus = BTreeSet::from_iter(command.cpus);

        let other_slices = "*.slice";
        let benchmark_slice = "benchmark.slice";

        let benchmark_ret = privs::with_escalated_privileges(|| {
            privs::verify_root().stack()?;

            find_or_create_slice(&systemctl_path, benchmark_slice).stack()?;

            restrict_slice(&systemctl_path, other_slices, &shielded_cpus, || {
                configure_benchmark_slice(
                    &systemctl_path,
                    benchmark_slice,
                    &shielded_cpus,
                    command.mem_bytes,
                    command.swap_mem_bytes,
                    command.enable_internet,
                )
                .stack()?;

                run_in_slice(
                    &systemd_run_path,
                    benchmark_slice,
                    &real_exe,
                    &command.args,
                    command.clear_env,
                    command.nice,
                )
                .stack()
            })
            .stack()
        })
        .stack()?;

        // Pretty much useless, since nothing important happens below here.
        // But good practice to explicitly, permanently drop privs when we don't need the anymore.
        privs::permanently_drop_privileges().stack()?;

        Ok(benchmark_ret)
    })
}

fn cpus_to_list(cpus: &BTreeSet<sys_config::Cpu>) -> String {
    cpus.iter()
        .map(std::string::ToString::to_string)
        .collect::<Vec<_>>()
        .join(",")
}

fn restrict_slice<F, T>(
    systemctl_path: &std::path::PathBuf,
    slice: &str,
    shielded_cpus: &BTreeSet<sys_config::Cpu>,
    func: F,
) -> Result<T>
where
    F: FnOnce() -> Result<T>,
{
    let all_cpus = sys_config::iter_cpus()
        .stack()?
        .iter()
        .map(|pair| pair.0)
        .collect::<BTreeSet<sys_config::Cpu>>();

    let unshielded_cpus = all_cpus
        .iter()
        .copied()
        .filter(|cpu| !shielded_cpus.contains(cpu))
        .collect::<BTreeSet<sys_config::Cpu>>();

    util::check_cmd(std::process::Command::new(systemctl_path).args([
        "set-property",
        "--runtime",
        "*.slice",
        &format!("AllowedCPUs={}", cpus_to_list(&unshielded_cpus)),
    ]))
    .context(slice.to_string())
    .stack()?;

    let ret = func();

    util::check_cmd(std::process::Command::new(systemctl_path).args([
        "set-property",
        "--runtime",
        "*.slice",
        &format!("AllowedCPUs={}", cpus_to_list(&all_cpus)),
    ]))
    .context(slice.to_string())
    .stack()?;

    ret
}

fn find_or_create_slice(systemctl_path: &std::path::PathBuf, slice: &str) -> Result<()> {
    find_slice(systemctl_path, slice)
        .or_else(|_| {
            eprintln!("Slice {slice} not found. I will create it now.");
            create_slice(systemctl_path, slice)
                .context(anyhow!(
                    "
Did not find {slice} and unable to create.
This could be because you are using NixOS or your /etc/systemd/system is immutable.
In any case, please create a slice called {slice} with a Description, no other configuration.

1. For NixOS, There is a benchmark.nix you can use in the root of this Rust crate.
2. For others, you may find the source-code of benchmark.slice embedded in this repo."
                ))
                .stack()
        })
        .and_then(|()| {
            find_slice(systemctl_path, slice)
                .context(anyhow!(
                    "{slice} not found; I tried to create it, but it is still not found."
                ))
                .stack()
        })
}

fn find_slice(systemctl_path: &std::path::PathBuf, slice: &str) -> Result<()> {
    util::check_cmd(
        std::process::Command::new(systemctl_path).args(["list-unit-files", "benchmark.slice"]),
    )
    .context(slice.to_string())
    .stack()
}

fn create_slice(systemctl_path: &std::path::PathBuf, slice: &str) -> Result<()> {
    let slice_src = "[Unit]
Description=Slice dedicated to benchmarking programs
# https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html
";

    let slice_path = std::path::PathBuf::from("/etc/systemd/system/").join(slice);
    util::write_to_file(&slice_path, slice_src)
        .context(slice.to_string())
        .stack()?;

    util::check_cmd(std::process::Command::new(systemctl_path).args(["daemon-reload"])).stack()
}

fn configure_benchmark_slice(
    systemctl_path: &std::path::PathBuf,
    slice: &str,
    shielded_cpus: &BTreeSet<sys_config::Cpu>,
    mem_bytes: Option<u64>,
    swap_mem_bytes: Option<u64>,
    enable_internet: bool,
) -> Result<()> {
    // I need to reset /sys/fs/cgroups/benchmark.slice/memory.peak The
    // [Cgroups V2 documentation] says, "A write of any non-empty string
    // to this file resets it". However, when I try that, I get EINVAL,
    // perhaps due to hierarchy (this is not a leaf node). However,
    // `systemctl stop benchmark.slice` seems to do the trick.
    //
    // I am not sure the exact semantics of "stopping" a slice, but it
    // doesn't seem to prevent me from systemd-run-ing a process here.
    //
    // [Cgroups V2 documentation]: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory-interface-files
    util::check_cmd(std::process::Command::new(systemctl_path).args(["stop", "benchmark.slice"]))
        .stack()?;

    let mut configure_benchmark_slice = std::process::Command::new(systemctl_path);
    configure_benchmark_slice.args([
        "set-property",
        "--runtime",
        slice,
        &format!("AllowedCPUs={}", cpus_to_list(shielded_cpus)),
        "CPUAccounting=yes",
        "MemoryAccounting=yes",
    ]);
    if let Some(val) = mem_bytes {
        configure_benchmark_slice.arg(format!("MemoryMax={val}"));
    }
    if let Some(val) = swap_mem_bytes {
        configure_benchmark_slice.arg(format!("MemorySwapMax={val}"));
    }
    if !enable_internet {
        // 1. Access is granted when the checked IP address matches an entry in the IPAddressAllow= list.
        // 2. Otherwise, access is denied when the checked IP address matches an entry in the IPAddressDeny= list.
        // 3. Otherwise, access is granted.
        // Therefore, we will set both IPAddressAllow and IPAddressDeny
        configure_benchmark_slice.args(["IPAddressAllow=localhost", "IPAddressDeny=any"]);
    }
    util::check_cmd(&mut configure_benchmark_slice).stack()
}

fn run_in_slice(
    systemd_run_path: &std::path::PathBuf,
    slice: &str,
    exe: &std::path::PathBuf,
    args: &std::vec::Vec<String>,
    clear_env: bool,
    nice: Option<i8>,
) -> Result<std::process::ExitStatus> {
    let mut run_benchmark = std::process::Command::new(systemd_run_path);
    let user = nix::unistd::getuid();
    let group = nix::unistd::getgid();
    let mut chdir_arg = std::ffi::OsString::from("--working-directory=");
    chdir_arg.push(
        std::env::current_dir()
            .map_err(Error::from_err)
            .stack()?
            .into_os_string(),
    );
    run_benchmark.args([
        &format!("--slice={slice}"),
        "--property=SetLoginEnvironment=no",
        &format!("--uid={user}"),
        &format!("--gid={group}"),
        "--wait",
        "--pipe",
        "--quiet",
    ]);
    run_benchmark.arg(chdir_arg);
    if let Some(value) = nice {
        run_benchmark.arg(format!("--nice={value}"));
    }
    if !clear_env {
        run_benchmark.args(std::env::vars().map(|(key, val)| format!("--setenv={key}={val}")));
    }
    run_benchmark.arg(exe);
    run_benchmark.args(args);
    run_benchmark
        .status()
        .map_err(Error::from_err)
        .context(anyhow!("Error launching {:?}", run_benchmark))
        .stack()
}

const SYSTEMCTL_PATH: &str =
    "/nix/store/3zykdvv4pvs0k11z0bgc96wfjnjjzm4p-systemd-minimal-256.8/bin/systemctl";
const SYSTEMD_RUN_PATH: &str =
    "/nix/store/3zykdvv4pvs0k11z0bgc96wfjnjjzm4p-systemd-minimal-256.8/bin/systemd-run";
