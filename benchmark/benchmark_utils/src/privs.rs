/*!
 * To use this library,
 *
 * 1. Call `initially_reduce_privileges()` as the very first step in `main()`.
 *
 * 2. Call `with_escalated_privileges(|| { ... })` when you need to escalate.
 *
 * 3. Call `permanently_drop_privileges()` just after the last `with_escalate_privileges`.
 *
 * 4. Ensure your binary is owned by root and setuid.
 *
 * 5. Do not run as root, or else I will not know what user to de-escalate to.
 *    Run as user a binary owned by root, with setuid.
 *
 * For a reference on how Setuid works and how to implement it correctly, see [Setuid Demystified by Chen, Wagner, and Dean].
 *
 * [Setuid Demystified by Chen, Wagner, and Dean]: <https://people.eecs.berkeley.edu/~daw/papers/setuid-usenix02.pdf>
 * */

use nix::unistd::{getresgid, getresuid, setresgid, setresuid, ResGid, ResUid};
use stacked_errors::{bail, Error, Result, StackableErr};

/// Call at the beginning of main to reduce privileges temporarily, by moving
/// effective UID/GID to the saved UID/GID.
pub fn initially_reduce_privileges() -> Result<()> {
    // De-esclate group
    let group = getresgid().map_err(Error::from_err).stack()?;
    setresgid(group.real, group.real, group.saved)
        .map_err(Error::from_err)
        .stack()?;
    if getresgid().map_err(Error::from_err).stack()?
        != (ResGid {
            real: group.real,
            effective: group.real,
            saved: group.saved,
        })
    {
        bail!("setresgid exceeded, but did not de-escalate");
    }

    // De-escalate user first
    let user = getresuid().map_err(Error::from_err).stack()?;
    if user.real == user.effective {
        bail!("Is this binary setuid and owned by another user?");
    }
    setresuid(user.real, user.real, user.saved)
        .map_err(Error::from_err)
        .stack()?;
    if getresuid().map_err(Error::from_err).stack()?
        != (ResUid {
            real: user.real,
            effective: user.real,
            saved: user.saved,
        })
    {
        bail!("setresuid exceeded, but did not de-escalate");
    }

    Ok(())
}

/// Run `func` with escalated privileges attained by setting effective UID/GID
/// set to saved UID/GID.
pub fn with_escalated_privileges<F, T>(func: F) -> Result<T>
where
    F: FnOnce() -> Result<T>,
{
    // Escalate user first
    let user = getresuid().map_err(Error::from_err).stack()?;
    setresuid(user.real, user.saved, user.saved)
        .map_err(Error::from_err)
        .stack()?;
    if getresuid().map_err(Error::from_err).stack()?
        != (ResUid {
            real: user.real,
            effective: user.saved,
            saved: user.saved,
        })
    {
        bail!("setresuid exceeded, but did not escalate");
    }

    // Esclate group
    let group = getresgid().map_err(Error::from_err).stack()?;
    setresgid(group.real, group.saved, group.saved)
        .map_err(Error::from_err)
        .stack()?;
    if getresgid().map_err(Error::from_err).stack()?
        != (ResGid {
            real: group.real,
            effective: group.saved,
            saved: group.saved,
        })
    {
        bail!("setresgid exceeded, but did not escalate");
    }

    let ret = func();

    // De-esclate group
    setresgid(group.real, group.effective, group.saved)
        .map_err(Error::from_err)
        .stack()?;
    if getresgid().map_err(Error::from_err).stack()?
        != (ResGid {
            real: group.real,
            effective: group.effective,
            saved: group.saved,
        })
    {
        bail!("setresgid exceeded, but did not de-escalate");
    }

    // De-escalate user first
    setresuid(user.real, user.effective, user.saved)
        .map_err(Error::from_err)
        .stack()?;
    if getresuid().map_err(Error::from_err).stack()?
        != (ResUid {
            real: user.real,
            effective: user.effective,
            saved: user.saved,
        })
    {
        bail!("setresuid exceeded, but did not de-escalate");
    }

    ret
}

/// Permanently drop privileges by assinging effective and saved UID/GID from
/// the real UID/GID.
///
/// If this return Err, please don't ignore it. An attacker may be tricking your
/// setuid bin into doing something malicious with more privilege than intended.
pub fn permanently_drop_privileges() -> Result<()> {
    // Drop group first
    let group = getresgid().map_err(Error::from_err).stack()?;
    setresgid(group.real, group.real, group.real)
        .map_err(Error::from_err)
        .stack()?;
    if getresgid().map_err(Error::from_err).stack()?
        != (ResGid {
            real: group.real,
            effective: group.real,
            saved: group.real,
        })
    {
        bail!("setresgid exceeded, but did not de-escalate");
    }
    // Drop user
    let user = getresuid().map_err(Error::from_err).stack()?;
    setresuid(user.real, user.real, user.real)
        .map_err(Error::from_err)
        .stack()?;
    if getresuid().map_err(Error::from_err).stack()?
        != (ResUid {
            real: user.real,
            effective: user.real,
            saved: user.real,
        })
    {
        bail!("setresuid exceeded, but did not de-escalate");
    }

    Ok(())
}

pub fn verify_safe_to_run_as_root(path: &std::path::PathBuf) -> Result<()> {
    use std::os::unix::fs::MetadataExt;
    if !path.exists() {
        bail!("{:?} does not exist; try building with Nix?", path);
    }
    let metadata = std::fs::metadata(path).map_err(Error::from_err).stack()?;
    if metadata.uid() != 0 || metadata.gid() != 0 || metadata.mode() & 0o002 != 0 {
        bail!("We will run {:?} as root, so it should be owned by root, root-group, and not world-writable", path);
    }
    Ok(())
}

pub fn verify_root() -> Result<()> {
    let real_uid = nix::unistd::geteuid();
    if !real_uid.is_root() {
        bail!("Not actually root, we are only {real_uid}");
    }
    Ok(())
}

pub fn verify_not_root() -> Result<()> {
    let real_uid = nix::unistd::geteuid();
    if real_uid.is_root() {
        bail!("We actually are root");
    }
    Ok(())
}
