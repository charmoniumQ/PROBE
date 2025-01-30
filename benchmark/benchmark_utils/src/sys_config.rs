use crate::privs;
use crate::util;
use serde::{Deserialize, Serialize};
use stacked_errors::{anyhow, bail, Error, Result, StackableErr};

#[derive(Serialize, Deserialize, Default, Debug)]
pub struct SysConfig {
    /// This control is used to define the rough relative IO cost of swapping
    /// and filesystem paging, as a value between 0 and 200. At 100, the VM
    /// assumes equal IO cost and will thus apply memory pressure to the page
    /// cache and swap-backed pages equally; lower values signify more expensive
    /// swap IO, higher values indicates cheaper.
    ///
    /// See [docs.kernel.org](https://docs.kernel.org/admin-guide/sysctl/vm.html#swappiness)
    swappiness: u8,

    /// Determines which capacities are needed to access perf event counters/tracers.
    ///
    /// RR-debugger requires this to be at most 1.
    ///
    /// See [docs.kernel.org](https://docs.kernel.org/admin-guide/sysctl/kernel.html#perf-event-paranoid)
    perf_event_paranoid: u8,

    cpus: std::collections::BTreeMap<Cpu, CpuConfig>,
}

#[derive(Serialize, Deserialize, Default, Debug)]
struct CpuConfig {
    /// The scaling governor currently attached to this policy.
    ///
    /// See [docs.kernel.org](https://docs.kernel.org/admin-guide/pm/cpufreq.html#policy-interface-in-sysfs)
    cpufreq_scaling_governor: Option<String>,

    /// Whether or not to deploy tasks to this CPU.
    ///
    /// E.g., We may disable the SMT-sibling CPU in order to protect this one
    /// from noise.
    online: Option<u8>,
}

impl SysConfig {
    /// Create a config appropriate for benchmarking.
    pub fn benchmarking_config(cpus: &[Cpu]) -> Result<SysConfig> {
        Ok(SysConfig {
            swappiness: 1,
            perf_event_paranoid: 1,
            cpus: cpus
                    .iter()
                    .map(|cpu| (
                        *cpu,
                        CpuConfig {
                            cpufreq_scaling_governor: Some("performance".to_string()),
                            online: Some(1),
                        },
                    ))
                    .chain(
                        cpus
                            .iter()
                            .map(|cpu| {
                                Ok(get_smt_sibling_cpus(*cpu)
                                   .stack()?
                                   .iter()
                                   .inspect(|sibling_cpu| {
                                       if cpus.contains(sibling_cpu) {
                                           eprintln!("You selected two CPUs from the same SMT group. This has less predictable performance.");
                                       }
                                   })
                                   .filter(|sibling_cpu| cpus.contains(sibling_cpu))
                                   .map(|sibling_cpu| {
                                       (
                                           // Disable sibling hypercores/SMT
                                           *sibling_cpu,
                                           CpuConfig {
                                               cpufreq_scaling_governor: None,
                                               online: Some(0),
                                           },
                                       )
                                   })
                                   .collect::<Vec<(u16, CpuConfig)>>()
                                )
                            })
                            .collect::<Result<Vec<Vec<(u16, CpuConfig)>>>>()
                            .stack()?
                            .into_iter()
                            .flat_map(std::iter::IntoIterator::into_iter)
                    )
                    .collect::<std::collections::BTreeMap<u16, CpuConfig>>()
        })
    }

    /// Temporarily set this config, run func, and unset.
    pub fn temporarily_set<F, T>(&self, func: F) -> Result<T>
    where
        F: FnOnce() -> Result<T>,
    {
        let old_config = SysConfig::read().stack()?;
        self.set().stack()?;
        let ret = func();
        old_config.set().stack()?;
        ret
    }

    /// Read current config of system.
    pub fn read() -> Result<SysConfig> {
        Ok(SysConfig {
            swappiness: std::fs::read_to_string(SWAPPINESS)
                .context(SWAPPINESS)
                .stack()?
                .trim()
                .parse()
                .context(SWAPPINESS)
                .stack()?,
            perf_event_paranoid: std::fs::read_to_string(PERF_EVENT_PARANOID)
                .context(PERF_EVENT_PARANOID)
                .stack()?
                .trim()
                .parse()
                .context(PERF_EVENT_PARANOID)
                .stack()?,
            cpus: iter_cpus()
                .stack()?
                .iter()
                .map(|(cpu_id, path)| {
                    Ok((
                        *cpu_id,
                        CpuConfig {
                            cpufreq_scaling_governor: std::fs::read_to_string(
                                path.join(CPU_FREQ_SCALING_GOVERNOR),
                            )
                                .ok()
                                .map(|value| value.trim().parse())
                                .transpose()
                                .context(CPU_ONLINE)
                                .stack()?,
                            online: std::fs::read_to_string(path.join(CPU_ONLINE))
                                .ok()
                                .map(|value| value.trim().parse())
                                .transpose()
                                .context(CPU_ONLINE)
                                .stack()?,
                        },
                    ))
                })
                .collect::<Result<Vec<_>>>()
                .stack()?
                .into_iter()
                .collect(),
        })
    }

    /// Set this config on the system.
    pub fn set(&self) -> Result<()> {
        let cpu_path = std::path::PathBuf::from(CPU_PATH);
        privs::with_escalated_privileges(|| {
            if !nix::unistd::geteuid().is_root() {
                bail!(
                    "Need more privilege; I am only {:?}",
                    nix::unistd::geteuid()
                );
            }
            util::eprintln_error(
                util::write_to_file(SWAPPINESS, &self.swappiness.to_string()).stack(),
            );
            util::eprintln_error(
                util::write_to_file(PERF_EVENT_PARANOID, &self.perf_event_paranoid.to_string())
                    .stack(),
            );
            // Set online
            for (cpu_id, cpu_config) in &self.cpus {
                let this_cpu_path = cpu_path.join("cpu".to_owned() + &cpu_id.to_string());
                let cpu_online_path = this_cpu_path.join(CPU_ONLINE);
                if let Some(state) = cpu_config.online {
                    util::eprintln_error(
                        util::write_to_file(&cpu_online_path, &state.to_string())
                            .context(anyhow!("{cpu_online_path:?}"))
                            .stack(),
                    );
                }
                let is_cpu_online = cpu_config.online.unwrap_or_else(|| {
                    std::fs::read_to_string(cpu_online_path)
                        .unwrap_or("0".to_owned())
                        .trim()
                        .parse::<u8>()
                        .unwrap_or(0)
                }) == 1;
                // Set scaling gov, if CPU is online
                let freq_scaling_path = this_cpu_path.join(CPU_FREQ_SCALING_GOVERNOR);
                if is_cpu_online {
                    if let Some(state) = &cpu_config.cpufreq_scaling_governor {
                        util::eprintln_error(
                            util::write_to_file(&freq_scaling_path, state)
                                .context(anyhow!("{freq_scaling_path:?}"))
                                .stack(),
                        );
                    }
                }
            }
            Ok(())
        })
    }
}

/// Iterate over CPUs in the Sisyphus (sysfs).
pub fn iter_cpus() -> Result<Vec<(Cpu, std::path::PathBuf)>> {
    let cpu_path = std::path::PathBuf::from(CPU_PATH);
    std::fs::read_dir(&cpu_path)
        .map_err(Error::from_err)
        .context(anyhow!("read_dir({:?}) failed", cpu_path))
        .stack()?
        .map(|maybe_dirent| {
            let dirent = maybe_dirent.map_err(Error::from_err)?;
            Ok((
                dirent.path(),
                dirent
                    .file_name()
                    .into_string()
                    .map_err(|err| anyhow!("Failed to decode {:?} {:?}", dirent.path(), err))
                    .stack()?,
            ))
        })
        .collect::<Result<Vec<_>>>()
        .context("Failed while getting dirent paths")
        .stack()?
        .into_iter()
        .filter(|(_, file_name)| file_name.starts_with("cpu") && file_name.chars().nth(3).is_some_and(|c| c.is_ascii_digit()))
        .map(|(path, file_name)| Ok((file_name[3..].parse().map_err(Error::from_err).context(file_name).stack()?, path)))
        .collect::<Result<Vec<_>>>()
        .context("Failed while parsing cpu file name to int")
        .stack()
}

fn get_smt_sibling_cpus(cpu: Cpu) -> Result<Vec<Cpu>> {
    let path = std::path::PathBuf::from(CPU_PATH)
        .join("cpu".to_owned() + &cpu.to_string())
        .join(SMT_SIBLINGS_LIST);
    Ok(std::fs::read_to_string(&path)
       .context(anyhow!("{path:?}"))
       .stack()?
       .split(',')
       .map(|part| {
           part.trim()
               .parse::<Cpu>()
               .map_err(|_| anyhow!("{} not parsable", part))
       })
       .collect::<Result<Vec<Cpu>>>()
       .stack()?
       .into_iter()
       .filter(|sibling_cpu| *sibling_cpu != cpu)
       .collect())
}

const SWAPPINESS: &str = "/proc/sys/vm/swappiness";
const PERF_EVENT_PARANOID: &str = "/proc/sys/kernel/perf_event_paranoid";
const CPU_PATH: &str = "/sys/devices/system/cpu/";
const CPU_FREQ_SCALING_GOVERNOR: &str = "cpufreq/scaling_governor";
const CPU_ONLINE: &str = "online";
const SMT_SIBLINGS_LIST: &str = "topology/thread_siblings_list";

/// Bring CPU offline and online.
pub fn reboot_cpu(cpu: Cpu) -> Result<()> {
    let path = std::path::PathBuf::from(CPU_PATH)
        .join("cpu".to_owned() + &cpu.to_string())
        .join(CPU_ONLINE);
    util::write_to_file(&path, "0").stack()?;
    util::write_to_file(&path, "1").stack()?;
    Ok(())
}

pub type Cpu = u16;
