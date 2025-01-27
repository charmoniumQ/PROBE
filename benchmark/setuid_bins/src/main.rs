use std::path::{Path, PathBuf};
use clap::Parser;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::io::{Read, Write};
use anyhow::{Result, Context, anyhow};

#[derive(Parser, Debug)]
#[command(version, about)]
enum Command {
    GetConfig {
        config: PathBuf,
    },
    SetConfig {
        config: PathBuf,
    },
    DropFileCache,
    NiceAndCpuSet,
}

#[derive(Serialize, Deserialize)]
struct Config {
    swappiness: u8,

    // https://wiki.archlinux.org/title/CPU_frequency_scaling#Setting_via_sysfs_(intel_pstate)
    intel_p_state_no_turbo: Option<u8>,

    // https://wiki.archlinux.org/title/CPU_frequency_scaling#Setting_via_sysfs_(other_scaling_drivers)
    cpufreq_boost: Option<u8>,

    perf_event_paranoid: u8,

    cpus: BTreeMap<u16, CpuConfig>,
}

#[derive(Serialize, Deserialize, Default)]
struct CpuConfig {
    // https://wiki.archlinux.org/title/CPU_frequency_scaling#Scaling_governors
    cpufreq_scaling_governor: String,

    // https://wiki.archlinux.org/title/CPU_frequency_scaling#Intel_performance_and_energy_bias_hint
    energy_perf_bias: Option<u8>,

    // Used to disable SMT
    online: Option<u8>,
}

const SWAPPINESS: &'static str = "/proc/sys/vm/swappiness";
const INTEL_P_STATE_NO_TURBO: &'static str = "/sys/devices/system/cpu/intel_pstate/no_turbo";
const CPU_FREQ_BOOST: &'static str = "/sys/devices/system/cpu/cpufreq/boost";
const PERF_EVENT_PARANOID: &'static str = "/proc/sys/kernel/perf_event_paranoid";
const CPU_PATH: &'static str = "/sys/devices/system/cpu/cpu";
const CPU_FREQ_SCALING_GOVERNOR: &'static str = "cpufreq/scaling_governor";
const CPU_ENERGY_PERF_BIAS: &'static str = "power/energy_perf_bias";
const CPU_ONLINE: &'static str = "online";

fn get_config() -> Result<Config> {
    Ok(Config {
        swappiness: std::fs::read_to_string(SWAPPINESS).context(SWAPPINESS)?.trim().parse().context(SWAPPINESS)?,
        intel_p_state_no_turbo: std::fs::read_to_string(INTEL_P_STATE_NO_TURBO).ok().map(|value| value.trim().parse().context(INTEL_P_STATE_NO_TURBO)).transpose()?,
        cpufreq_boost: std::fs::read_to_string(CPU_FREQ_BOOST).ok().map(|value| value.trim().parse().context(CPU_FREQ_BOOST)).transpose()?,
        perf_event_paranoid: std::fs::read_to_string(PERF_EVENT_PARANOID).context(PERF_EVENT_PARANOID)?.trim().parse().context(PERF_EVENT_PARANOID)?,
        cpus: glob::glob(&(CPU_PATH.to_owned() + "*"))?.map(|alleged_path| {
            let path = alleged_path?;
            let file_name = path.file_name().ok_or(anyhow!("{:?} does not have file name", path))?.to_str().ok_or(anyhow!("File name of {:?} not decodable", path))?;
            Ok(file_name[3..].parse().ok().map(|cpu_id| Ok((cpu_id, CpuConfig {
                cpufreq_scaling_governor: std::fs::read_to_string(path.join(CPU_FREQ_SCALING_GOVERNOR)).context(CPU_FREQ_SCALING_GOVERNOR)?,
                energy_perf_bias: std::fs::read_to_string(path.join(CPU_ENERGY_PERF_BIAS)).ok().map(|value| value.trim().parse()).transpose().context(CPU_ENERGY_PERF_BIAS)?,
                online: std::fs::read_to_string(path.join(CPU_ONLINE)).ok().map(|value| value.trim().parse()).transpose().context(CPU_ONLINE)?,
            }))))
        }).collect::<Result<Vec<_>>>()?.into_iter().filter_map(|x| x).collect::<Result<Vec<_>>>()?.into_iter().collect(),
    })
}

fn write_to_file(path_str: String, content: String) -> Result<()> {
    let path = Path::new(&path_str);
    if path.exists() {
        let is_already_written = {
            let mut file = std::fs::OpenOptions::new().read(true).open(path)?;
            let mut buffer = vec![0; content.len()];
            let read_bytes = file.read(&mut buffer[..])?;
            read_bytes == buffer.len() && buffer == content.as_bytes()
        };
        if !is_already_written {
            let mut file = std::fs::OpenOptions::new().write(true).open(path)?;
            file.write_all(content.as_bytes())?;
            file.sync_all()?;
        }
        Ok(())
    } else {
        Err(anyhow!("File {:?} does not exist", path))
    }
}

fn non_fatal_result<T>(result: anyhow::Result<T>) -> Option<T> {
    match result {
        Ok(val) => Some(val),
        Err(err) => {
            eprintln!("Non-fatal error: {:?}", err);
            None
        },
    }
}

fn set_config(config: Config) -> Result<()> {
    non_fatal_result(write_to_file(
        SWAPPINESS.to_owned(),
        config.swappiness.to_string(),
    ));
    config.intel_p_state_no_turbo.map(|state| non_fatal_result(write_to_file(
        INTEL_P_STATE_NO_TURBO.to_owned(),
        state.to_string(),
    )));
    config.cpufreq_boost.map(|state| non_fatal_result(write_to_file(
        CPU_FREQ_BOOST.to_owned(),
        state.to_string(),
    )));
    non_fatal_result(write_to_file(
        PERF_EVENT_PARANOID.to_owned(),
        config.perf_event_paranoid.to_string(),
    ));
    for (cpu_id, cpu_config) in config.cpus {
        non_fatal_result(write_to_file(
            CPU_PATH.to_owned() + &cpu_id.to_string() + "/" + CPU_FREQ_SCALING_GOVERNOR,
            cpu_config.cpufreq_scaling_governor,
        ));
        cpu_config.energy_perf_bias.map(|state|
            non_fatal_result(write_to_file(
                CPU_PATH.to_owned() + &cpu_id.to_string() + "/" + CPU_ENERGY_PERF_BIAS,
                state.to_string(),
            ))
        );
        cpu_config.online.map(|state| non_fatal_result(write_to_file(
            CPU_PATH.to_owned() + &cpu_id.to_string() + "/" + CPU_ONLINE,
            state.to_string(),
        )));
    }
    Ok(())
}

fn main() -> Result<()> {
    let command = Command::parse();
    match command {
        Command::GetConfig { config: ref config_path } => {
            let config_file = std::fs::OpenOptions::new().write(true).open(config_path)?;
            let config = get_config()?;
            serde_yaml::to_writer(config_file, &config)?;
        },
        Command::SetConfig { config: ref config_path } => {
            let config_file = std::fs::OpenOptions::new().read(true).open(config_path)?;
            let config = serde_yaml::from_reader(config_file)?;
            set_config(config)?;
        },
        _ => {
            return Err(anyhow!("{:?} not implemented yet", command));
        },
    }
    Ok(())
}
