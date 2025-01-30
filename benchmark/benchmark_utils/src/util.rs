use stacked_errors::{anyhow, bail, Error, Result, StackableErr};
use std::io::{Read, Write};

pub fn eprintln_error<T>(result: Result<T>) -> Option<T> {
    match result {
        Ok(val) => Some(val),
        Err(err) => {
            eprintln!("Non-fatal error: {err:?}");
            None
        }
    }
}

pub fn write_to_file<P: AsRef<std::path::Path> + std::fmt::Debug>(
    path: P,
    content: &str,
) -> Result<()> {
    if path.as_ref().exists() {
        let is_already_written = {
            let mut file = std::fs::OpenOptions::new()
                .read(true)
                .open(path.as_ref())
                .map_err(Error::from_err)
                .stack()?;
            let mut buffer = vec![0; content.len()];
            let read_bytes = file
                .read(&mut buffer[..])
                .map_err(Error::from_err)
                .stack()?;
            read_bytes == buffer.len() && buffer == content.as_bytes()
        };
        if !is_already_written {
            let mut file = std::fs::OpenOptions::new()
                .write(true)
                .open(path.as_ref())
                .map_err(Error::from_err)
                .stack()?;
            file.write_all(content.as_bytes())
                .map_err(Error::from_err)
                .stack()?;
            //file.sync_all().map_err(Error::from_err).stack()?;
        }
        Ok(())
    } else {
        bail!("File {:?} does not exist", path)
    }
}

pub fn check_cmd(cmd: &mut std::process::Command) -> Result<()> {
    if !cmd
        .stdout(std::process::Stdio::piped())
        .status()
        .map_err(Error::from_err)
        .context(anyhow!("Error launching {:?}", cmd))
        .stack()?
        .success()
    {
        bail!("Command failed: {:?}", cmd)
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
