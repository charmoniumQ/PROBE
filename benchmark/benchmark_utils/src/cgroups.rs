use serde::{Deserialize, Serialize};
use stacked_errors::{anyhow, bail, Error, Result, StackableErr};

/// Represents the resource utilization of a process in a Cgroup.
///
/// Ideally, only the process itself, its children, and negligible processes run
/// in that cgroup.
#[derive(Serialize, Deserialize, Default, Debug)]
pub struct Rusage {
    cpu_user_us: u64,
    cpu_system_us: u64,
    peak_memory_usage: u64,
    walltime_us: u64,
    returncode: i32,
    signal: i32,
}

impl std::ops::Sub for Rusage {
    type Output = Rusage;
    /// Subtracts one resource utilization struct from another.
    fn sub(self, rhs: Rusage) -> Rusage {
        Rusage {
            cpu_user_us: self.cpu_user_us - rhs.cpu_user_us,
            cpu_system_us: self.cpu_system_us - rhs.cpu_system_us,
            peak_memory_usage: rhs.peak_memory_usage,
            walltime_us: self.walltime_us - rhs.walltime_us,
            returncode: self.returncode,
            signal: self.signal,
        }
    }
}

/// Represents the name of a Cgroup.
pub struct Cgroup {
    path: std::path::PathBuf,
}

impl Cgroup {
    /// Gets the Cgroup of the current process.
    pub fn current() -> Result<Cgroup> {
        let proc_self_cgroup = std::fs::read_to_string(PROC_SELF_CGROUP)
            .map_err(Error::from_err)
            .stack()?;
        proc_self_cgroup
            .split(':')
            .last()
            .ok_or(anyhow!(
                "Malformatted {:?} containing: {:?}\n",
                PROC_SELF_CGROUP,
                proc_self_cgroup
            ))
            .map_err(Error::from_err)
            .stack()
            .and_then(|cgroup_str| -> Result<Cgroup> {
                let trimmed_cgroup_str = cgroup_str.trim();
                let mut path = std::path::PathBuf::from(CGROUPS_PATH);
                path.push(&trimmed_cgroup_str[1..]);
                if path.exists() {
                    Ok(Cgroup { path })
                } else {
                    bail!("Expected cgroup path does not exist: {:?}\n", path)
                }
            })
    }

    /// Get resource usage of Cgroup since counter reset.
    pub fn get_rusage(&self, maybe_status: Option<std::process::ExitStatus>) -> Result<Rusage> {
        use std::os::unix::process::ExitStatusExt;

        let mut memory_peak_path = self.path.clone();
        memory_peak_path.push(MEMORY_PEAK);

        let mut cpu_stat_path = self.path.clone();
        cpu_stat_path.push(CPU_STAT);
        let cpu_stat = std::fs::read_to_string(cpu_stat_path)
            .map_err(Error::from_err)
            .stack()?;

        let walltime_us = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(Error::from_err)
            .stack()?
            .as_micros();

        Ok(Rusage {
            cpu_user_us: find_between(&cpu_stat, "user_usec ", "\n")
                .ok_or(anyhow!("Expected user_usec in: {:?}\n", &cpu_stat))
                .stack()?
                .parse::<u64>()
                .stack()?,
            cpu_system_us: find_between(&cpu_stat, "system_usec ", "\n")
                .ok_or(anyhow!("Expected system_usec in: {:?}\n", cpu_stat))
                .stack()?
                .parse::<u64>()
                .stack()?,
            peak_memory_usage: std::fs::read_to_string(&memory_peak_path)
                .map_err(Error::from_err)
                .stack()?
                .trim()
                .parse::<u64>()
                .map_err(Error::from_err)
                .context(anyhow!("{:?}\n", memory_peak_path))
                .stack()?,
            walltime_us: u64::try_from(walltime_us).context(walltime_us).stack()?,
            returncode: maybe_status.map_or(0, |status| status.code().unwrap_or(0)),
            signal: maybe_status.map_or(0, |status| status.signal().unwrap_or(0)),
        })
    }
}

fn find_between(main: &str, pre: &str, post: &str) -> Option<String> {
    let start_idx = main.find(pre)? + pre.len();
    let stop_idx = start_idx + main[start_idx..].find(post)?;
    Some(main[start_idx..stop_idx].to_owned())
}

const PROC_SELF_CGROUP: &str = "/proc/self/cgroup";
const CGROUPS_PATH: &str = "/sys/fs/cgroup/";
const MEMORY_PEAK: &str = "memory.peak";
const CPU_STAT: &str = "cpu.stat";
