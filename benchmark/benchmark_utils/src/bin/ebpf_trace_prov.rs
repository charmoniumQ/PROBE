use benchmark_utils::{privs, util};
use clap::Parser;
use serde::Deserialize;
use stacked_errors::{anyhow, bail, Error, StackableErr};

/*
 * Debug me with:
 *
 *   nix develop
 *   ./deploy_setuid.sh run
 *   ./target/release/ebpf_trace_prov --log-file log --print-bpftrace 2>prov.bt ls
 *   $EDITOR prov.bt
 *   pid=   # pid of process you want to trace (try Bash)
 *   sudo $NIX_BPFTRACE_PATH/bin/bpftrace -B line -f json -d all -p $pid -o log - $pid < prov.bt
 */

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Temporarily installs eBPF tracers to trace command"
)]
struct Command {
    /// Soft limit on CPU seconds.
    #[arg(long, default_value = "ebpf.log")]
    log_file: std::path::PathBuf,

    /// Print the generated bpftrace source to stderr
    #[arg(long)]
    print_bpftrace: bool,

    /// Timeout for waiting for eBPF to launch in seconds
    #[arg(long, default_value_t = 8.0)]
    ebpf_timeout: f64,

    /// Print the generated bpftrace source
    #[arg(long)]
    verbose: bool,

    /// Executable to run with resource limits
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with2(244, || {
        privs::initially_reduce_privileges().stack()?;

        #[allow(clippy::const_is_empty)]
        if NIX_BPFTRACE_PATH.is_empty() {
            bail!("Could not find NIX_BPFTRACE_PATH in env vars at build time");
        }

        let bpftrace = std::path::PathBuf::from(NIX_BPFTRACE_PATH.to_owned()).join("bin/bpftrace");
        privs::verify_safe_to_run_as_root(&bpftrace).stack()?;

        let command = Command::parse();

        let mut cmd = std::process::Command::new(&command.cmd[0]);
        cmd.args(&command.cmd[1..]);
        let cmd_proc = util::spawn_stopped(cmd, command.verbose).stack()?;

        util::write_to_file_truncate(&command.log_file, "").stack()?;

        let bpftrace_source = create_bpftrace_source();
        if command.print_bpftrace {
            eprintln!("{bpftrace_source}");
        }

        let dir = tempdir::TempDir::new("ebpf_trace_prov")
            .map_err(Error::from_err)
            .stack()?;

        let bpftrace_source_file = dir.path().join("bpftrace_source");

        let mut bpftrace_cmd = std::process::Command::new(bpftrace);
        bpftrace_cmd.args(["-B", "line", "-f", "json"]);
        if command.verbose {
            bpftrace_cmd.args(["-d", "all"]);
        }
        bpftrace_cmd.args([
            "-p".into(),
            (&cmd_proc.to_string()).into(),
            "-o".into(),
            Into::<std::ffi::OsString>::into(&command.log_file),
            (&bpftrace_source_file).into(),
            (&cmd_proc.to_string()).into(),
        ]);
        // Adding some extra because JSON takes up some space
        bpftrace_cmd.env("BPFTRACE_MAX_STRLEN", (100 + libc::PATH_MAX).to_string());
        bpftrace_cmd.stdin(std::process::Stdio::piped());

        if command.verbose {
            eprintln!("{bpftrace_cmd:?}");
        }

        let mut bpftrace_proc = privs::with_escalated_privileges(|| {
            util::write_to_file_truncate(&bpftrace_source_file, &bpftrace_source).stack()?;
            bpftrace_cmd.spawn().map_err(Error::from_err).stack()
        })?;
        privs::permanently_drop_privileges().stack()?;

        let timeout = std::time::Duration::from_secs_f64(command.ebpf_timeout);
        util::sleepy_wait(timeout, SLEEP_DURATION, command.verbose, || {
            match std::fs::read_to_string(&command.log_file)
                .map_err(Error::from_err)
                .stack()
            {
                Ok(contents) => {
                    if contents.contains("launch_pid") {
                        Ok(Some(()))
                    } else {
                        if command.verbose {
                            eprintln!("{contents:?}");
                        }
                        Ok(None)
                    }
                }
                Err(err) => Err(err),
            }
        })
        .stack()?
        .ok_or_else(|| anyhow!("bpftrace not launched within {timeout:?}\n"))
        .stack()?;

        // Wak eup cmd_proc
        nix::sys::signal::kill(cmd_proc, nix::sys::signal::Signal::SIGCONT)
            .map_err(Error::from_err)
            .stack()?;

        let cmd_status = nix::sys::wait::waitpid(cmd_proc, None);

        bpftrace_proc.wait().map_err(Error::from_err).stack()?;

        dir.close().map_err(Error::from_err).stack()?;

        cmd_status.map_err(Error::from_err).stack()
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
