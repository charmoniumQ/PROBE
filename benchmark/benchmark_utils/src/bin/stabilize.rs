use clap::Parser;
use stacked_errors::{anyhow, Result, StackableErr};
use std::path::PathBuf;

use benchmark_utils::privs;
use benchmark_utils::sys_config;
use benchmark_utils::util;

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Steps to stabalize the benchmarking of the given command",
    long_about = "

The following changes are made to the /sys and /proc FS, and the original state
is recorded and restored after execution is complete. If things go absolutely
wrong, you can always reboot as none of these changes are persistent:

- Turns off swap. If the program's working set goes to swap, performance
  benchmarks are meaningless, and you need to try on a system with more RAM. We
  would want to error out in that condition.

- Turns of SMT on the sibling core, giving stronger isolation from processes on
  that other core.

- Enables perf event paranoid. This is needed for RR to operate.

- Turns CPU
 frequency scaling on performance.

- Turns power-saving off.

- Optionally, sync & drop the FS cache.

The following actions affect the spawned process:

- Sets process priority.

- Drops privileges. Nearly all of the changes in this section and the previous
  require privileges. This binary should be setuid and owned by root. We will
  drop privileges before executing the command under test. Please read the
  source code to ensure we aren't going to do anything malicious or wrong.

"
)]
struct Command {
    /// At the end of execution, we will restore the system to the state
    /// described by this file.
    ///
    /// The system configuration will be recorded and stored here if it does not exist.
    ///
    /// We use a file, rather than storing the old configuration in RAM, because
    /// we want to persistently remember the original state even if this program
    /// gets killed.
    #[arg(long, default_value = "pre_benchmark_config.yaml")]
    config_path: std::path::PathBuf,

    /// Whether to sync and drop the file cache.
    #[arg(long, default_value_t = false)]
    drop_file_cache: bool,

    /// Priority (aka niceness), also used for IO priority
    #[arg(long)]
    prio: Option<i32>,

    /// Executable to run
    exe: std::path::PathBuf,

    /// Arguments passed to exe
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    args: Vec<String>,
}

fn main() -> Result<()> {
    privs::initially_reduce_privileges();

    // Check stuff before starting
    let setpriv_path = PathBuf::from(SETPRIV_PATH);
    privs::verify_safe_to_run_as_root(&setpriv_path)?;

    let command = Command::parse();

    // Store current config
    // OR
    // Read config from config file
    // The system will be returned to this state after completion
    if !command.config_path.exists() {
        let orig_config = sys_config::SysConfig::read().stack()?;
        let file = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(command.config_path.clone())
            .context(anyhow!("{:?}", command.config_path))
            .stack()?;
        serde_yaml::to_writer(file, &orig_config).stack()?;
    } else {
        let file = std::fs::OpenOptions::new()
            .read(true)
            .open(command.config_path.clone())
            .stack()?;
        let orig_config: sys_config::SysConfig = serde_yaml::from_reader(file).stack()?;
        // Reset to this known state.
        // If the rest of it crashes terrbily, at least we reset yours system to the state specified by the file.
        privs::with_escalated_privileges(|| orig_config.set().stack())?;
    }

    // Last unprivileged setup
    let cpu = sys_config::pick_cpu();
    let benchmark_config = sys_config::SysConfig::benchmarking_config(cpu).stack()?;
    let ruid = nix::unistd::getuid();
    let rgid = nix::unistd::getgid();
    assert!(!ruid.is_root(), "If Real UID is root, then I don't know who to de-escalate privileges to. Please run this binary as your user, but owned by root and setuid.");

    // Escalate privs
    privs::with_escalated_privileges(|| {
        // Verify Effective and Real UID is root, because cset will fail otherwise
        // We need root Effective ID, so our writes-to-files will succeed.
        // We need root Real ID so children (e.g., cset) will have privileged capabilities
        if !nix::unistd::geteuid().is_root() {
            return Err(anyhow!("Privilege escalation did not succeed"));
        }

        // Upgrade process priority (aka nice) and io priority
        change_priority(command.prio, command.prio).stack()?;

        // Change config using /proc and /sys
        // Don't worry, the enclosing function changes it back after this callback is done.
        benchmark_config
            .temporarily_change_config(|| {
                sys_config::reboot_cpu(cpu).stack()?;

                // Dropping cache should be close to the end.
                if command.drop_file_cache {
                    drop_file_cache().stack()?;
                }

                // We want to de-escalate before running user-code.
                // Apparently, we aren't supposed to use su for that anymore
                // http://jdebp.info/FGA/dont-abuse-su-for-dropping-privileges.html
                // We don't need to manipulate env. vars. since we never truly logged in as root, just escalated with setuid.
                let mut main_cmd = std::process::Command::new(setpriv_path);
                main_cmd.args([
                    &format!("--reuid={}", ruid),
                    &format!("--regid={}", rgid),
                    "--clear-groups",
                    // For good measure
                    "--inh-caps=-all",
                ]);
                main_cmd.arg(command.exe);
                main_cmd.args(command.args);

                util::check_cmd(main_cmd, false).stack()
            })
            .stack()
    })
    .stack()?;

    // Pretty much useless, since nothing important happens below here.
    // But good practice to explicitly, permanently drop privs when we don't need the anymore.
    privs::permanently_drop_privileges();

    Ok(())
}

fn change_priority(prio: Option<i32>, ioprio: Option<i32>) -> Result<()> {
    // https://www.man7.org/linux/man-pages/man2/setpriority.2.html
    //
    //   A child created by fork(2) inherits its parent's nice value.  The
    //   nice value is preserved across execve(2).
    //
    if let Some(real_prio) = prio {
        let ret1 = unsafe { libc::setpriority(libc::PRIO_PROCESS, 0, real_prio) };
        if ret1 != 0 {
            return Err(anyhow!("setpriority returned errno {:?}", unsafe {
                *libc::__errno_location()
            }));
        }
    }
    if let Some(real_ioprio) = ioprio {
        // https://www.man7.org/linux/man-pages/man2/ioprio_set.2.html
        //
        //   Two or more processes or threads can share an I/O context.  This
        //   will be the case when clone(2) was called with the CLONE_IO flag.
        //   However, by default, the distinct threads of a process will not
        //   share the same I/O context.
        //
        // Therefore, I will set io prio for the whole process group

        // This is not defined in libc crate
        // https://docs.rs/libc/latest/libc/?search=ioprio
        // So I do
        // echo '#include <linux/ioprio.h>\n#include <stdio.h>\nint main() { printf("%d\n", IOPRIO_WHO_PGRP); }' | gcc -x c - && ./a.out && rm a.out
        const IOPRIO_WHO_PGRP: i32 = 2;
        let ret2 = unsafe { libc::syscall(libc::SYS_ioprio_set, IOPRIO_WHO_PGRP, 0, real_ioprio) };
        if ret2 != 0 {
            return Err(anyhow!("setpriority returned errno {:?}", unsafe {
                *libc::__errno_location()
            }));
        }
    }
    Ok(())
}

fn drop_file_cache() -> Result<()> {
    nix::unistd::sync();
    util::write_to_file("/proc/sys/vm/drop_caches".to_string(), "3".to_string())?;
    Ok(())
}

// Hardcoding paths to the binaries we execute because we have setuid
const SETPRIV_PATH: &str =
    "/nix/store/ndqpb82si5a7znlb4wa84sjncl4mvgqm-util-linux-2.39.4-bin/bin/setpriv";
