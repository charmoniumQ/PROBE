use num_traits::NumCast;
use stacked_errors::{anyhow, bail, Error, Result, StackableErr};
use std::io::Write;

pub fn eprintln_error<T>(result: Result<T>) -> Option<T> {
    match result {
        Ok(val) => Some(val),
        Err(err) => {
            eprintln!("Non-fatal error: {err:?}");
            None
        }
    }
}

/// This function writes to a file, e.g., sysfs or procs.
pub fn write_to_sys_file<P: AsRef<std::path::Path> + std::fmt::Debug>(
    path: P,
    content: &str,
) -> Result<()> {
    if path.as_ref().exists() {
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .open(path.as_ref())
            .map_err(Error::from_err)
            .context(anyhow!("{path:?}\n"))
            .stack()?;
        file.write_all(content.as_bytes())
            .map_err(Error::from_err)
            .context(anyhow!("{path:?}\n"))
            .stack()?;
        Ok(())
    } else {
        bail!("File {:?} does not exist\n", path)
    }
}

pub fn write_to_file_truncate<P: AsRef<std::path::Path> + std::fmt::Debug>(
    path: P,
    content: &str,
) -> Result<()> {
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(path.as_ref())
        .map_err(Error::from_err)
        .context(anyhow!("{path:?}\n"))
        .stack()?;
    file.write_all(content.as_bytes())
        .map_err(Error::from_err)
        .context(anyhow!("{path:?}\n"))
        .stack()?;
    Ok(())
}

pub fn check_cmd(cmd: &mut std::process::Command) -> Result<()> {
    if !cmd
        .stdout(std::process::Stdio::piped())
        .status()
        .map_err(Error::from_err)
        .context(anyhow!("Error launching {:?}\n", cmd))
        .stack()?
        .success()
    {
        bail!("Command failed: {:?}\n", cmd)
    }
    Ok(())
}

/// The default impl of [`std::process::Termination`] for [Result]
/// converts [Err] to [`std::process::FAILURE`].
///
/// For wrapper programs that execute a user-supplied command in a child
/// process, I would rather return a different error code for Err, so I can tell
/// whether `main()` returned `Err`, or whether it is propagating the
/// return-code of the client program (which will likely be
/// [`std::process::SUCCESS`] or [`std::process::FAILURE`]). I will pick an error
/// code that is less likely to occur in the child to indicate errors in the
/// wrapper.
///
/// I can't re-define [`std::process::Termination`], since trait-impls-for-struct
/// can only be defined in the module defining the trait or the module defining
/// the struct.
pub fn replace_err_with<F>(err_exit_code: u8, real_main: F) -> std::process::ExitCode
where
    F: FnOnce() -> Result<std::process::ExitStatus>,
{
    match real_main() {
        Ok(status) => {
            use std::os::unix::process::ExitStatusExt;
            if let Some(signal) = status.signal() {
                eprintln!("Child terminated by signal {signal}.");
            }
            if status.core_dumped() {
                eprintln!("Child's core dumped.");
            }
            if let Some(signal) = status.stopped_signal() {
                eprintln!("Child stopped by signal {signal} (not actually terminated, I think). Hopefully, std::process::Command::wait never returns this.");
            }
            if status.continued() {
                eprintln!("Child continued (not actually terminated, I think). Hopefully, std::process::Command::wait never returns this.");
            }
            if status.success() {
                std::process::ExitCode::SUCCESS
            } else if let Some(code) = status.code() {
                eprintln!("Child exited with error code {code}.");
                // If the child was able to return an extended exitcode (32-bit rather than 8-bit), we should be able to as well.
                std::process::exit(code)
            } else {
                eprintln!("Child died with no exitcode. If it was killed by a signal, you will see that above.");
                std::process::ExitCode::from(err_exit_code)
            }
        }
        Err(err) => {
            if let Ok(wrapper) = std::env::current_exe() {
                eprintln!("Wrapper {wrapper:?} failed:\n{err:?}");
            } else {
                eprintln!("Wrapper program failed:\n{err:?}");
            }
            std::process::ExitCode::from(err_exit_code)
        }
    }
}

pub fn replace_err_with2<F>(err_exit_code: u8, real_main: F) -> std::process::ExitCode
where
    F: FnOnce() -> Result<nix::sys::wait::WaitStatus>,
{
    use nix::sys::wait::WaitStatus::{
        Continued, Exited, PtraceEvent, PtraceSyscall, Signaled, StillAlive, Stopped,
    };
    match real_main() {
        Ok(status) => match status {
            Exited(_, exit_code) => {
                eprintln!("Child exited with {exit_code}.");
                u8::try_from(exit_code).unwrap_or_else(|err| {
                    eprintln!(
                        "Child exit code {exit_code} not in u8-range, using {err_exit_code}. {err:?}"
                    );
                    err_exit_code
                }).into()
            }
            Signaled(_, exit_code, core_dump) => {
                eprintln!("Child signaled with {exit_code}.");
                if core_dump {
                    eprintln!("Child's core dumped.");
                }
                err_exit_code.into()
            }
            PtraceEvent(_, sig, _) => {
                eprintln!("Child ptraced with {sig}.");
                err_exit_code.into()
            }
            PtraceSyscall(_) => {
                eprintln!("Child got ptraced");
                err_exit_code.into()
            }
            Continued(_) => {
                eprintln!("Child got continued");
                err_exit_code.into()
            }
            StillAlive => {
                eprintln!("Child is still alive");
                err_exit_code.into()
            }
            Stopped(_, _) => {
                eprintln!("Child got stopped");
                err_exit_code.into()
            }
        },
        Err(err) => {
            if let Ok(wrapper) = std::env::current_exe() {
                eprintln!("Wrapper {wrapper:?} failed:\n{err:?}");
            } else {
                eprintln!("Wrapper program failed:\n{err:?}");
            }
            err_exit_code.into()
        }
    }
}

pub fn sleepy_wait<T, F>(
    timeout: std::time::Duration,
    sleep: std::time::Duration,
    verbose: bool,
    func: F,
) -> Result<Option<T>>
where
    F: Fn() -> Result<Option<T>>,
{
    if std::time::Duration::ZERO >= timeout {
        bail!("{timeout:?} should be positive\n");
    }
    if std::time::Duration::ZERO >= sleep {
        bail!("{sleep:?} should be positive\n");
    }
    let iterations: u16 = <u16 as NumCast>::from(timeout.div_duration_f64(sleep).round())
        .ok_or_else(|| anyhow!("{timeout:?} / {sleep:?} not convertable\n"))
        .stack()?;
    for iteration in 0..iterations {
        let ret = func();
        match ret {
            Ok(Some(ret)) => return Ok(Some(ret)),
            Ok(None) => {
                std::thread::sleep(sleep);
                nix::sched::sched_yield().map_err(Error::from_err).stack()?;
                if verbose {
                    println!("Sleeping for {sleep:?} ({iteration}th / {iterations})");
                }
            }
            Err(err) => return Err(err),
        }
    }
    Ok(None)
}

/// Spawn cmd in stopped state
pub fn spawn_stopped(mut proc: std::process::Command, verbose: bool) -> Result<nix::unistd::Pid> {
    let parent_pid = nix::unistd::getpid();
    match unsafe { nix::unistd::fork() }.map_err(Error::from_err)? {
        nix::unistd::ForkResult::Parent { child } => {
            nix::sys::wait::waitpid(child, Some(nix::sys::wait::WaitPidFlag::WSTOPPED))
                .map_err(Error::from_err)
                .stack()?;
            Ok(child)
        }
        nix::unistd::ForkResult::Child => {
            use std::os::unix::process::CommandExt;
            let child_pid = nix::unistd::getpid();
            if child_pid == parent_pid {
                nix::unistd::write(
                    std::io::stdout(),
                    "after fork, child_pid == parent_pid. Something is wrong\n".as_bytes(),
                )
                .ok();
                unsafe { libc::_exit(111) };
            }
            if verbose {
                nix::unistd::write(std::io::stdout(), "Issuing SIGSTP\n".as_bytes()).ok();
            }
            if nix::sys::signal::kill(child_pid, nix::sys::signal::Signal::SIGTSTP).is_err() {
                nix::unistd::write(
                    std::io::stdout(),
                    "Error issuing SIGSTP; exiting\n".as_bytes(),
                )
                .ok();
                unsafe { libc::_exit(112) };
            }
            if verbose {
                nix::unistd::write(std::io::stdout(), "Awoken from SIGSTP\n".as_bytes()).ok();
            }
            proc.exec();
            nix::unistd::write(std::io::stdout(), "Error occurred during exec\n".as_bytes()).ok();
            unsafe { libc::_exit(113) };
        }
    }
}
