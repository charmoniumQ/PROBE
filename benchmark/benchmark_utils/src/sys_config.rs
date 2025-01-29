use serde::{Deserialize, Serialize};
use stacked_errors::{anyhow, Error, Result, StackableErr};

use crate::util::{eprintln_error, write_to_file};

#[derive(Serialize, Deserialize, Default, Debug)]
pub struct SysConfig {
    /// This control is used to define the rough relative IO cost of swapping
    /// and filesystem paging, as a value between 0 and 200. At 100, the VM
    /// assumes equal IO cost and will thus apply memory pressure to the page
    /// cache and swap-backed pages equally; lower values signify more expensive
    /// swap IO, higher values indicates cheaper.
    ///
    /// https://docs.kernel.org/admin-guide/sysctl/vm.html#swappiness
    swappiness: u8,

    /// Determines which capacities are needed to access perf event counters/tracers.
    ///
    /// RR-debugger requires this to be at most 1.
    ///
    /// https://docs.kernel.org/admin-guide/sysctl/kernel.html#perf-event-paranoid
    perf_event_paranoid: u8,

    cpus: std::collections::BTreeMap<Cpu, CpuConfig>,
}

#[derive(Serialize, Deserialize, Default, Debug)]
struct CpuConfig {
    /// The scaling governor currently attached to this policy.
    ///
    /// https://docs.kernel.org/admin-guide/pm/cpufreq.html#policy-interface-in-sysfs
    cpufreq_scaling_governor: Option<String>,

    /// Whether or not to deploy tasks to this CPU.
    ///
    /// E.g., We may disable the SMT-sibling CPU in order to protect this one
    /// from noise.
    online: Option<u8>,
}

impl SysConfig {
    pub fn benchmarking_config(cpu: Cpu) -> Result<SysConfig> {
        Ok(SysConfig {
            swappiness: 1,
            perf_event_paranoid: 1,
            cpus: std::collections::BTreeMap::from_iter(
                std::iter::once((
                    cpu,
                    CpuConfig {
                        cpufreq_scaling_governor: Some("performance".to_string()),
                        online: Some(1),
                    },
                ))
                .chain(get_smt_sibling_cpus(cpu).stack()?.iter().map(
                    |sibling_cpu| {
                        (
                            // Disable sibling hypercores/SMT
                            *sibling_cpu,
                            CpuConfig {
                                cpufreq_scaling_governor: Some("performance".to_string()),
                                online: Some(0),
                            },
                        )
                    },
                )),
            ),
        })
    }

    pub fn temporarily_change_config<F, T>(&self, func: F) -> Result<T>
    where
        F: FnOnce() -> Result<T>,
    {
        let old_config = SysConfig::read()?;
        self.set()?;
        let ret = func();
        old_config.set()?;
        ret
    }

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
            cpus: iter_cpus()?
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
                .collect::<Result<Vec<_>>>()?
                .into_iter()
                .collect(),
        })
    }

    pub fn set(&self) -> Result<()> {
        if !nix::unistd::geteuid().is_root() {
            return Err(anyhow!(
                "Need more privilege; I am only {:?}",
                nix::unistd::geteuid()
            ));
        }
        eprintln_error(write_to_file(SWAPPINESS.to_owned(), self.swappiness.to_string()).stack());
        eprintln_error(
            write_to_file(
                PERF_EVENT_PARANOID.to_owned(),
                self.perf_event_paranoid.to_string(),
            )
            .stack(),
        );
        // Set online
        for (cpu_id, cpu_config) in self.cpus.iter() {
            let cpu_online_path = format!("{}{}/{}", CPU_PATH, cpu_id, CPU_ONLINE);
            if let Some(state) = cpu_config.online {
                eprintln_error(
                    write_to_file(cpu_online_path.clone(), state.to_string())
                        .context(cpu_online_path.clone())
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
            let freq_scaling_path = format!("{}{}/{}", CPU_PATH, cpu_id, CPU_FREQ_SCALING_GOVERNOR);
            if is_cpu_online {
                if let Some(state) = &cpu_config.cpufreq_scaling_governor {
                    eprintln_error(
                        write_to_file(freq_scaling_path.clone(), state.clone())
                            .context(freq_scaling_path)
                            .stack(),
                    );
                }
            }
        }
        Ok(())
    }
}

pub fn iter_cpus() -> Result<Vec<(Cpu, std::path::PathBuf)>> {
    Ok(glob::glob(&(CPU_PATH.to_owned() + "*"))
        .map_err(Error::from_err)?
        .map(|alleged_path| {
            let path = alleged_path.map_err(Error::from_err)?;
            let file_name = path
                .file_name()
                .ok_or(anyhow!("{:?} does not have file name", path))?
                .to_str()
                .ok_or(anyhow!("File name of {:?} not decodable", path))?;
            Ok(file_name[3..].parse().ok().map(|cpu_id| (cpu_id, path)))
        })
        .collect::<Result<Vec<Option<_>>>>()?
        .into_iter()
        .flatten()
        .collect())
}

fn get_smt_sibling_cpus(cpu: Cpu) -> Result<Vec<Cpu>> {
    let path = CPU_PATH.to_owned() + &cpu.to_string() + "/" + SMT_SIBLINGS_LIST;
    Ok(std::fs::read_to_string(path.clone())
        .context(path)
        .stack()?
        .split(',')
        .map(|part| {
            part.trim()
                .parse::<Cpu>()
                .map_err(|_| anyhow!("{} not parsable", part))
        })
        .collect::<Result<Vec<Cpu>>>()?
        .into_iter()
        .filter(|sibling_cpu| *sibling_cpu != cpu)
        .collect())
}

const SWAPPINESS: &str = "/proc/sys/vm/swappiness";
const PERF_EVENT_PARANOID: &str = "/proc/sys/kernel/perf_event_paranoid";
const CPU_PATH: &str = "/sys/devices/system/cpu/cpu";
const CPU_FREQ_SCALING_GOVERNOR: &str = "cpufreq/scaling_governor";
const CPU_ONLINE: &str = "online";
const SMT_SIBLINGS_LIST: &str = "topology/thread_siblings_list";

pub fn pick_cpu() -> Cpu {
    eprintln!("TODO: Pick CPU smartly");
    3
}

pub fn reboot_cpu(cpu: Cpu) -> Result<()> {
    let path = format!("{}{}/{}", CPU_PATH, cpu, CPU_ONLINE);
    write_to_file(path.to_string(), 0.to_string()).stack()?;
    write_to_file(path.to_string(), 1.to_string()).stack()?;
    Ok(())
}

pub type Cpu = u16;
