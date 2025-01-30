use clap::Parser;
use stacked_errors::{anyhow, bail, Error, Result, StackableErr};

use benchmark_utils::privs;
use benchmark_utils::sys_config;
use benchmark_utils::util;

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Set configuration in /sys and /proc FS to stabalize the benchmarking of the given command",
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

- Turns CPU frequency scaling on performance (as opposed to power-saving or
  balanced configuration).

- Optionally, sync & drop the FS cache.

The following actions affect the spawned process:

- Sets process priority.

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
    config: std::path::PathBuf,

    /// Whether to sync and drop the file cache.
    #[arg(long, default_value_t = false)]
    drop_file_cache: bool,

    /// Priority (aka niceness), also used for IO priority
    #[arg(long)]
    prio: Option<i32>,

    /// Executable to run while the benchmark configuration is applied
    exe: String,

    /// Arguments passed to executable
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    args: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        privs::initially_reduce_privileges().stack()?;

        let command = Command::parse();

        store_or_apply_stored_config(&command.config).stack()?;

        // Last unprivileged setup
        let cpu = sys_config::pick_cpu();
        let benchmark_config = sys_config::SysConfig::benchmarking_config(cpu).stack()?;

        privs::verify_not_root().stack()?;

        // Escalate privs
        privs::with_escalated_privileges(|| {
            // Verify Effective and Real UID is root, because cset will fail otherwise
            // We need root Effective ID, so our writes-to-files will succeed.
            // We need root Real ID so children (e.g., cset) will have privileged capabilities
            privs::verify_root().stack()?;

            // Upgrade process priority (aka nice) and io priority
            change_priority(command.prio, command.prio).stack()?;

            // Dropping cache should be close to the end.
            if command.drop_file_cache {
                drop_file_cache().stack()?;
            }

            // Rebooting the CPU forces kernel threads to move to another core, at least temporarily
            sys_config::reboot_cpu(cpu).stack()?;

            Ok(())
        })
        .stack()?;

        // Change config using /proc and /sys
        // Don't worry, the enclosing function changes it back after this callback is done, win, loose, or draw.
        // Also this will acquire its own privileges.
        let cmd_ret = benchmark_config
            .temporarily_set(|| {
                let mut main_cmd = std::process::Command::new(command.exe);
                main_cmd.args(command.args);
                main_cmd
                    .status()
                    .map_err(Error::from_err)
                    .context(anyhow!("Error launching {:?}", main_cmd))
                    .stack()
            })
            .stack();

        // Pretty much useless, since nothing important happens below here.
        // But good practice to explicitly, permanently drop privs when we don't need the anymore.
        privs::permanently_drop_privileges().stack()?;

        cmd_ret
    })
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
            bail!("setpriority returned errno {:?}", unsafe {
                *libc::__errno_location()
            });
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
            bail!("setpriority returned errno {:?}", unsafe {
                *libc::__errno_location()
            });
        }
    }
    Ok(())
}

fn drop_file_cache() -> Result<()> {
    nix::unistd::sync();
    util::write_to_file("/proc/sys/vm/drop_caches", "3").stack()?;
    Ok(())
}

/// Read config from config file, if exists.
/// Otherwise, record config to file.
fn store_or_apply_stored_config(config_path: &std::path::PathBuf) -> Result<()> {
    if config_path.exists() {
        let file = std::fs::OpenOptions::new()
            .read(true)
            .open(config_path)
            .stack()?;
        let orig_config: sys_config::SysConfig = serde_json::from_reader(file).stack()?;
        // Reset to this known state.
        // If the rest of it crashes terrbily, at least we reset yours system to the state specified by the file.
        orig_config.set().stack()?;
    } else {
        let orig_config = sys_config::SysConfig::read().stack()?;
        let file = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(config_path)
            .context(anyhow!("{:?}", config_path))
            .stack()?;
        serde_json::to_writer(file, &orig_config).stack()?;
    }
    Ok(())
}
