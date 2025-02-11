use benchmark_utils::{privs, util};
use clap::Parser;
use serde::Deserialize;
use stacked_errors::{anyhow, bail, Error, StackableErr};

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Temporarily installs eBPF tracers to trace command"
)]
struct Command {
    /// Soft limit on CPU seconds.
    #[arg(long)]
    log_file: std::path::PathBuf,

    /// Print the generated bpftrace source
    #[arg(long)]
    print_bpftrace: bool,

    /// Timeout for waiting for eBPF to launch in seconds
    #[arg(long, default_value_t = 4.0)]
    ebpf_timeout: f64,

    /// Print the generated bpftrace source
    #[arg(long)]
    verbose: bool,

    /// Executable to run with resource limits
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        privs::initially_reduce_privileges().stack()?;

        let start_stopped = std::env::current_exe()
            .map_err(Error::from_err)
            .stack()?
            .parent()
            .ok_or(anyhow!("Current exe has no parent"))
            .stack()?
            .join(if cfg!(debug_assertions) {
                "target/debug/start_stopped"
            } else {
                "target/release/start_stopped"
            });
        if !start_stopped.exists() {
            bail!("{start_stopped:?} does not exist. Please run `cargo build`");
        }

        let bpftrace = std::path::PathBuf::from(NIX_BPFTRACE_PATH.to_owned()).join("bin/bpftrace");
        privs::verify_safe_to_run_as_root(&bpftrace).stack()?;

        let command = Command::parse();

        let mut cmd = std::process::Command::new(start_stopped);
        if command.verbose {
            cmd.arg("--verbose");
        }
        // Start env because bpftrace tracks the first exec after bpftrace starts up
        // We want to track the orignal program
        // so we launch this one first basically
        cmd.arg("env");
        cmd.args(&command.cmd);
        let mut cmd_proc = cmd.spawn().map_err(Error::from_err).stack()?;

        let tmp_dir = tempdir::TempDir::new("ebpf_trace_prov")
            .map_err(Error::from_err)
            .stack()?;

        util::write_to_file_truncate(&command.log_file, "").stack()?;

        let mut bpftrace_proc = privs::with_escalated_privileges(|| {
            let bpftrace_file = tmp_dir.path().to_owned().join("log");

            let bpftrace_source = create_bpftrace_source();
            util::write_to_file_truncate(&bpftrace_file, &bpftrace_source).stack()?;
            if command.print_bpftrace {
                eprintln!("{bpftrace_source}");
            }

            let mut bpftrace_cmd = std::process::Command::new(bpftrace);
            bpftrace_cmd.args([
                "-B", "line", "-f", "json", /* TODO: For some reason, text doesn't work */
            ]);
            if command.verbose {
                bpftrace_cmd.args(["-d", "all"]);
            }
            bpftrace_cmd.args([
                "-p".into(),
                (&cmd_proc.id().to_string()).into(),
                "-o".into(),
                Into::<std::ffi::OsString>::into(&command.log_file),
                Into::<std::ffi::OsString>::into(&bpftrace_file),
                (&cmd_proc.id().to_string()).into(),
            ]);
            // Adding some extra because JSON takes up some space
            bpftrace_cmd.env("BPFTRACE_MAX_STRLEN", (100 + libc::PATH_MAX).to_string());
            let mut bpftrace_proc = bpftrace_cmd.spawn().map_err(Error::from_err).stack()?;

            assert!(0.0 < command.ebpf_timeout);
            let timeout = std::time::Duration::from_secs_f64(command.ebpf_timeout);
            let iterations_f = timeout.div_duration_f64(SLEEP_DURATION).ceil();
            let iterations: u16 = util::checked_cast(iterations_f).unwrap_or_else(|| {
                panic!("Could not convert {timeout:?} / {SLEEP_DURATION:?} = {iterations_f} to int")
            });
            let mut started = false;
            for iter in 0..iterations {
                if command.verbose {
                    println!(
                        "{iter}: {:?}",
                        std::fs::read_to_string(&command.log_file)
                            .map_err(Error::from_err)
                            .stack()?
                    );
                }
                if std::fs::read_to_string(&command.log_file)
                    .map_err(Error::from_err)
                    .stack()?
                    .contains("launch_pid")
                {
                    started = true;
                    break;
                }
                std::thread::sleep(SLEEP_DURATION);
                nix::sched::sched_yield().map_err(Error::from_err).stack()?;
                if let Some(status) = bpftrace_proc.try_wait().map_err(Error::from_err).stack()? {
                    bail!("bpftrace exited unexpectedly with {:?}", status);
                }
            }
            if !started {
                bail!("bpftrace not launched within {timeout:?}");
            }

            Ok(bpftrace_proc)
        })
        .stack()?;

        #[allow(clippy::cast_possible_wrap)]
        let signed_pid = cmd_proc.id() as i32;
        while !std::fs::read_to_string(format!("/proc/{signed_pid}/wchan"))
            .map_err(Error::from_err)
            .stack()?
            .starts_with("do_signal_stop")
        {
            nix::sched::sched_yield().map_err(Error::from_err).stack()?;
        }
        nix::sys::signal::kill(
            nix::unistd::Pid::from_raw(signed_pid),
            nix::sys::signal::Signal::SIGCONT,
        )
        .map_err(Error::from_err)
        .stack()?;

        let cmd_status = cmd_proc.wait().map_err(Error::from_err).stack();

        bpftrace_proc.wait().map_err(Error::from_err).stack()?;

        privs::permanently_drop_privileges().stack()?;

        cmd_status
    })
}

const NIX_BPFTRACE_PATH: &str = env!("NIX_BPFTRACE_PATH");
const BPFTRACE_SOURCE: &str = include_str!("../../bpftrace_prov.bt");
const SYSCALL_INFOS: &str = include_str!("../../syscalls.yaml");

#[derive(Deserialize)]
struct SyscallInfo {
    name: String,
    args: Vec<SyscallArgs>,
}

#[derive(Deserialize)]
struct SyscallArgs {
    name: String,
    #[serde(rename = "type")]
    type_: SyscallType,
}
#[derive(Deserialize)]
#[serde(untagged)]
enum SyscallType {
    Literal(String),
    Struct(Vec<StructMember>),
}
#[derive(Deserialize)]
struct StructMember {
    name: String,
    #[serde(rename = "type")]
    type_: String,
}

fn create_bpftrace_source() -> String {
    let syscall_infos: Vec<SyscallInfo> = serde_yaml::from_str(SYSCALL_INFOS).unwrap();
    std::iter::once(BPFTRACE_SOURCE.to_owned())
        .chain(
            syscall_infos
                .iter()
                .flat_map(|s| create_enter_hook(s).into_iter()),
        )
        .collect::<Vec<String>>()
        .into_iter()
        .chain(create_exit_hooks(&syscall_infos))
        .collect()
}

fn create_enter_hook(syscall_info: &SyscallInfo) -> Vec<String> {
    [
        "tracepoint:syscalls:sys_enter_".to_owned(),
        syscall_info.name.clone(),
        "\n{\n".to_owned(),
        "  if (@track_pids[pid]) {\n".to_owned(),
        "    printf(\"%d,%d,%d,syscall_enter,%d".to_owned(),
    ]
    .into_iter()
    .chain(syscall_info.args.iter().map(|arg| {
        match &arg.type_ {
            SyscallType::Literal(type_) => ",".to_owned() + printf_code(type_),
            SyscallType::Struct(struct_members) => struct_members
                .iter()
                .map(|member| ",".to_owned() + printf_code(&member.type_))
                .collect(),
        }
    }))
    .chain(["\\n\", pid, tid, nsecs, args->__syscall_nr".to_owned()])
    .chain(syscall_info.args.iter().map(|arg| {
        match &arg.type_ {
            SyscallType::Literal(type_) => {
                if type_ == "char*" {
                    format!(", str(args->{})", arg.name).to_owned()
                } else {
                    format!(", args->{}", arg.name).to_owned()
                }
            }
            SyscallType::Struct(struct_members) => struct_members
                .iter()
                .map(|member| {
                    if member.type_ == "char*" {
                        format!(", str(args->{}->{})", arg.name, member.name).to_owned()
                    } else {
                        format!(", args->{}->{}", arg.name, member.name).to_owned()
                    }
                })
                .collect(),
        }
    }))
    .chain([");\n".to_owned(), "  }\n".to_owned(), "}\n\n\n".to_owned()])
    .collect()
}

fn create_exit_hooks(syscall_infos: &[SyscallInfo]) -> Vec<String> {
    syscall_infos.iter().map(|syscall_info| format!("tracepoint:syscalls:sys_exit_{},\n", syscall_info.name)).chain([
        "\n{\n".to_owned(),
        "  if (@track_pids[pid]) {\n".to_owned(),
        "    printf(\"%d,%d,%d,syscall_exit,%d,%d\\n\", pid, tid, nsecs, args->__syscall_nr, args->ret);\n".to_owned(),
        "  }\n".to_owned(),
        "}\n\n\n".to_owned(),
    ]).collect()
}

fn printf_code(type_: &str) -> &str {
    match type_ {
        "int" | "uid_t" | "gid_t" => "%d",
        "unsigned int" => "%u",
        "u64" => "%lu",
        "char*" => "%s",
        "char**" | "ptr" => "%p",
        "mode_t" => "%03o",
        _ => panic!("{type_} is not defined"),
    }
}

const SLEEP_DURATION: std::time::Duration = std::time::Duration::from_millis(100);
