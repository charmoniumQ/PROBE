use crate::util;
use serde::{Deserialize, Serialize};
use stacked_errors::{anyhow, Error, Result, StackableErr};

#[derive(Serialize, Deserialize, Default, Debug)]
pub struct Rusage {
    cpu_user_us: u64,
    cpu_system_us: u64,
    peak_memory_usage: u64,
    walltime_us: u64,
}

impl std::ops::Sub for Rusage {
    type Output = Rusage;
    fn sub(self, rhs: Rusage) -> Rusage {
        Rusage {
            cpu_user_us: self.cpu_user_us - rhs.cpu_user_us,
            cpu_system_us: self.cpu_system_us - rhs.cpu_system_us,
            peak_memory_usage: rhs.peak_memory_usage,
            walltime_us: self.walltime_us - rhs.walltime_us,
        }
    }
}

pub struct Cgroup {
    path: std::path::PathBuf,
}

impl Cgroup {
    pub fn current() -> Result<Cgroup> {
        let proc_self_cgroup = std::fs::read_to_string(PROC_SELF_CGROUP)
            .map_err(Error::from_err)
            .stack()?;
        proc_self_cgroup
            .split(':')
            .last()
            .ok_or(anyhow!(
                "Malformatted {:?} containing: {:?}",
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
                    Err(anyhow!("Expected cgroup path does not exist: {:?}", path))
                }
            })
    }
    pub fn reset_counters(&self) -> Result<()> {
        // https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory-interface-files
        // A write of any non-empty string to this file resets it to the current memory usage for subsequent reads through the same file descriptor.
        let mut memory_peak_path = self.path.clone();
        memory_peak_path.push(MEMORY_PEAK);
        // util::write_to_file2(&memory_peak_path, "0".to_string()).stack()
        Ok(())
    }
    pub fn get_rusage(&self) -> Result<Rusage> {
        let mut memory_peak_path = self.path.clone();
        memory_peak_path.push(MEMORY_PEAK);

        let mut cpu_stat_path = self.path.clone();
        cpu_stat_path.push(CPU_STAT);
        let cpu_stat = std::fs::read_to_string(cpu_stat_path)
            .map_err(Error::from_err)
            .stack()?;

        Ok(Rusage {
            cpu_user_us: find_between(cpu_stat.clone(), "user_usec ", "\n")
                .ok_or(anyhow!("Expected user_usec in: {:?}", cpu_stat.clone()))
                .stack()?
                .parse::<u64>()
                .stack()?,
            cpu_system_us: find_between(cpu_stat.clone(), "system_usec ", "\n")
                .ok_or(anyhow!("Expected system_usec in: {:?}", cpu_stat.clone()))
                .stack()?
                .parse::<u64>()
                .stack()?,
            peak_memory_usage: std::fs::read_to_string(memory_peak_path.clone())
                .map_err(Error::from_err)
                .stack()?
                .trim()
                .parse::<u64>()
                .map_err(Error::from_err)
                .stack()
                .context(anyhow!("{:?}", memory_peak_path))?,
            walltime_us: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_err(Error::from_err)
                .stack()?
                .as_micros() as u64,
        })
    }
}

fn find_between(main: String, pre: &str, post: &str) -> Option<String> {
    let start_idx = main.find(&pre)? + pre.len();
    let stop_idx = start_idx + main[start_idx..].find(&post)?;
    Some(main[start_idx..stop_idx].to_owned())
}

const PROC_SELF_CGROUP: &str = "/proc/self/cgroup";
const CGROUPS_PATH: &str = "/sys/fs/cgroup/";
const MEMORY_PEAK: &str = "memory.peak";
const CPU_STAT: &str = "cpu.stat";
