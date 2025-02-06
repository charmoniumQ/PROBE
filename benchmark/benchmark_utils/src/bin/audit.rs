use benchmark_utils::{privs, util};
use clap::Parser;
use stacked_errors::{anyhow, bail, Error, Result, StackableErr};

#[derive(Parser, Debug)]
#[command(
    version = "0.1.0",
    about = "Temporarily turns on auditd to observe the running of command"
)]
struct Command {
    /// Soft limit on CPU seconds.
    #[arg(long)]
    log_file: std::path::PathBuf,

    /// Directories in which to watch all operations
    #[arg(long, value_delimiter = ',')]
    directories: Vec<std::path::PathBuf>,

    /// Debug to stderr
    #[arg(long)]
    debug: bool,

    /// Executable to run with resource limits
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    cmd: Vec<String>,
}

fn main() -> std::process::ExitCode {
    util::replace_err_with(244, || {
        privs::initially_reduce_privileges().stack()?;

        let command = Command::parse();

        let status = audit(
            command.debug,
            command.directories.iter(),
            &command.log_file,
            || {
                let mut cmd = std::process::Command::new(&command.cmd[0]);
                cmd.args(&command.cmd[1..]);
                if command.debug {
                    println!("Command {cmd:?}\n");
                }
                cmd.status()
                    .context(anyhow!("Executing cmd {:?}", cmd))
                    .stack()
            },
        )
        .stack();

        privs::permanently_drop_privileges().stack()?;

        status
    })
}

#[allow(clippy::similar_names)]
fn audit<'a, F, T, P, I>(debug: bool, directories: I, log_file: P, func: F) -> Result<T>
where
    F: FnOnce() -> Result<T>,
    P: AsRef<std::path::Path>,
    I: Iterator<Item = &'a std::path::PathBuf>,
{
    use nix::sys::signal;
    use nix::unistd::Pid;

    let uid = nix::unistd::getuid();
    let gid = nix::unistd::getgid();
    let root_uid = nix::unistd::Uid::from_raw(0);
    let root_gid = nix::unistd::Gid::from_raw(0);

    let rules = get_rules(uid, gid, directories);

    let log_file = std::path::absolute(log_file)
        .map_err(Error::from_err)
        .stack()?;

    let auditd = std::path::PathBuf::from(NIX_AUDIT_PATH.to_owned() + "/bin/auditd");
    privs::verify_safe_to_run_as_root(&auditd).stack()?;
    let auditctl = std::path::PathBuf::from(NIX_AUDIT_PATH.to_owned() + "/bin/auditctl");
    privs::verify_safe_to_run_as_root(&auditctl).stack()?;

    let tmp_dir = tempdir::TempDir::new("auditd")
        .map_err(Error::from_err)
        .stack()?;

    let tmp_log_file = tmp_dir.path().to_owned().join("log");
    util::write_to_file_truncate(&tmp_log_file, "").stack()?;

    let conf_path = tmp_dir.path().to_owned().join("auditd.conf");
    let auditd_config = AUDITD_CONFIG
        .replace(
            "$LOG_FILE",
            tmp_log_file
                .to_str()
                .ok_or(anyhow!("Failed to decode {tmp_dir:?}"))
                .map_err(Error::from_err)
                .stack()?,
        )
        .trim()
        .to_owned()
        + "\n";
    util::write_to_file_truncate(&conf_path, &auditd_config).stack()?;

    if debug {
        println!("\nConfig:\n{}\n", &auditd_config);
    }

    let mut audit_proc = privs::with_escalated_privileges(|| {
        apply_auditd_rules(&auditctl, debug, &rules).stack()?;

        if is_auditd_running(&auditctl).stack()? {
            bail!("Auditd is already running. Try `sudo systemctl disable audit.service` or `sudo pkill auditd`");
        }

        nix::unistd::chown(tmp_dir.path(), Some(root_uid), Some(root_gid)).map_err(Error::from_err).stack()?;

        nix::unistd::chown(&conf_path, Some(root_uid), Some(root_gid)).map_err(Error::from_err).stack()?;

        nix::unistd::chown(&tmp_log_file, Some(root_uid), Some(root_gid)).map_err(Error::from_err).stack()?;

        let mut reset_proc = std::process::Command::new(&auditctl);
        reset_proc.args(["-e", "1", "-f", "1", "--reset-lost"]);
        util::check_cmd(&mut reset_proc).stack()?;

        let mut auditd_cmd = std::process::Command::new(&auditd);
        auditd_cmd.args([
            Into::<std::ffi::OsString>::into("-n"),
            Into::<std::ffi::OsString>::into("-c"),
            (&tmp_dir.path()).into(),
        ]);
        if debug {
            println!("NOT writing log events to log_file; instead, they will show up on stderr. This is how --debug works.");
            auditd_cmd.arg("-f");
        }
        let auditd_proc = auditd_cmd.spawn().stack()?;

        while !is_auditd_running(&auditctl).stack()? {
            if debug {
                println!("auditd is not running yet; looping.");
            }
            nix::sched::sched_yield().map_err(Error::from_err).stack()?;
        }

        Ok(auditd_proc)
    }).stack()?;

    if debug {
        println!();
    }
    let ret = func();
    if debug {
        println!();
    }

    privs::with_escalated_privileges(|| {
        #[allow(clippy::cast_possible_wrap)]
        let signed_pid = audit_proc.id() as i32;

        signal::kill(Pid::from_raw(signed_pid), signal::Signal::SIGTERM)
            .map_err(Error::from_err)
            .stack()?;

        let exit = audit_proc.wait().map_err(Error::from_err).stack()?;
        if !exit.success() {
            eprintln!("auditd exited with unknown error {exit:?}");
        }

        apply_auditd_rules(auditctl, debug, &vec![]).stack()?;

        std::fs::copy(&tmp_log_file, &log_file)
            .map_err(Error::from_err)
            .stack()?;

        std::os::unix::fs::chown(&log_file, Some(uid.into()), Some(gid.into()))
            .map_err(Error::from_err)
            .stack()?;

        std::fs::remove_dir_all(&tmp_dir)
            .map_err(Error::from_err)
            .stack()?;

        Ok(())
    })
    .stack()?;

    ret
}

fn is_auditd_running<P: AsRef<std::path::Path>>(auditctl: P) -> Result<bool> {
    let mut check_proc = std::process::Command::new(auditctl.as_ref());
    check_proc.arg("-s");
    let check_output = check_proc.output().map_err(Error::from_err).stack()?;
    let stdout = String::from_utf8_lossy(&check_output.stdout);
    let stderr = String::from_utf8_lossy(&check_output.stderr);
    if !check_output.status.success() {
        bail!("{check_proc:?} failed.\n{stdout:?}\n{stderr:?}");
    }
    match stdout.find("pid") {
        None => bail!("{check_proc:?} does not contain 'pid'.\n{stdout:?}\n{stderr:?}"),
        Some(idx) => Ok(stdout.chars().nth(idx + 4) != Some('0')),
    }
}

fn get_rules<'a, I>(
    uid: nix::unistd::Uid,
    gid: nix::unistd::Gid,
    directories: I,
) -> std::vec::Vec<std::vec::Vec<std::ffi::OsString>>
where
    I: Iterator<Item = &'a std::path::PathBuf>,
{
    type V = std::vec::Vec<std::ffi::OsString>;
    let arch = std::env::consts::ARCH;
    let std_opts: V = vec![
        "-a".into(),
        "always,exit".into(),
        "-F".into(),
        format!("arch={arch}").into(),
        "-F".into(),
        format!("uid={uid}").into(),
        "-F".into(),
        format!("gid={gid}").into(),
    ];
    std::iter::once(
        std_opts
            .clone()
            .into_iter()
            .chain([
                "-S".into(),
                "clone,clone3,fork,vfork,execve,execveat,exit,exit_group".into(),
                "-k".into(),
                "proc".into(),
            ])
            .collect::<V>(),
    )
    .chain(directories.map(|directory| {
        std_opts
            .clone()
            .into_iter()
            .chain([
                "-F".into(),
                {
                    let mut ret = std::ffi::OsString::from("dir=");
                    ret.push(directory);
                    ret
                },
                "-k".into(),
                "dir".into(),
            ])
            .collect::<V>()
    }))
    .collect()
}

fn apply_auditd_rules<P: AsRef<std::ffi::OsStr>>(
    auditctl: P,
    debug: bool,
    rules: &std::vec::Vec<std::vec::Vec<std::ffi::OsString>>,
) -> Result<()> {
    let mut audit_reset = std::process::Command::new(&auditctl);
    audit_reset.args(["-D"]);
    if debug {
        println!("Auditd reset: {audit_reset:?}");
    }
    util::check_cmd(&mut audit_reset).stack()?;

    for rule in rules {
        let mut audit_rule = std::process::Command::new(&auditctl);
        audit_rule.args(rule);
        if debug {
            println!("Auditd rule: {audit_rule:?}");
        }
        util::check_cmd(&mut audit_rule).stack()?;
    }

    if debug {
        let mut audit_list = std::process::Command::new(&auditctl);
        audit_list.arg("-l");
        if debug {
            println!("Auditd list: {audit_list:?}");
        }
        let audit_list_status = audit_list.status().context(anyhow!("")).stack()?;
        if !audit_list_status.success() {
            println!("Auditd list failed: {audit_list_status:?}");
        }
    }

    Ok(())
}

const NIX_AUDIT_PATH: &str = env!("NIX_AUDIT_PATH");

const AUDITD_CONFIG: &str = "
log_file = $LOG_FILE
log_format = ENRICHED
space_left = 100
space_left_action = suspend
";
