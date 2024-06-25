use machine_info::{Machine, SystemInfo};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct Metadata {
    entry_pid: libc::pid_t,
    arch: &'static str,
    system: SystemInfo,
}

impl Metadata {
    pub fn new(pid: libc::pid_t) -> Self {
        Self {
            entry_pid: pid,
            arch: std::env::consts::ARCH,
            system: Machine::new().system_info(),
        }
    }
}
