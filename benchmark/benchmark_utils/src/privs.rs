use stacked_errors::anyhow;

use once::assert_has_not_been_called;

const UID_MINUS_ONE: nix::unistd::Uid = nix::unistd::Uid::from_raw((-1_i32) as u32);
const GID_MINUS_ONE: nix::unistd::Gid = nix::unistd::Gid::from_raw((-1_i32) as u32);

// For a reference on how Setuid works and how to implement it correctly, see
// https://people.eecs.berkeley.edu/~daw/papers/setuid-usenix02.pdf
// Setuid Demystified by Chen, Wagner, and Dean
// This work will use the simplified abstraction shown in Figure 13.

/// Call at the beginning of
pub fn initially_reduce_privileges() {
    assert_has_not_been_called!();

    use nix::unistd::*;

    // De-esclate group
    let resgid = getresgid().unwrap();
    setresgid(resgid.real, resgid.real, GID_MINUS_ONE).unwrap();
    if getresgid().unwrap()
        != (ResGid {
            real: resgid.real,
            effective: resgid.real,
            saved: resgid.saved,
        })
    {
        panic!("setresgid exceeded, but did not de-escalate");
    }

    // De-escalate user first
    let resuid = getresuid().unwrap();
    setresuid(resuid.real, resuid.real, UID_MINUS_ONE).unwrap();
    if getresuid().unwrap()
        != (ResUid {
            real: resuid.real,
            effective: resuid.real,
            saved: resuid.saved,
        })
    {
        panic!("setresuid exceeded, but did not de-escalate");
    }
}

pub fn with_escalated_privileges<F, T>(func: F) -> T
where
    F: FnOnce() -> T,
{
    use nix::unistd::*;

    // Escalate user first
    let resuid = getresuid().unwrap();
    setresuid(UID_MINUS_ONE, resuid.saved, UID_MINUS_ONE).unwrap();
    if getresuid().unwrap()
        != (ResUid {
            real: resuid.real,
            effective: resuid.saved,
            saved: resuid.saved,
        })
    {
        panic!("setresuid exceeded, but did not escalate");
    }

    // Esclate group
    let resgid = getresgid().unwrap();
    setresgid(GID_MINUS_ONE, resgid.saved, GID_MINUS_ONE).unwrap();
    if getresgid().unwrap()
        != (ResGid {
            real: resgid.real,
            effective: resgid.saved,
            saved: resgid.saved,
        })
    {
        panic!("setresgid exceeded, but did not escalate");
    }

    let ret = func();

    // De-esclate group
    setresgid(GID_MINUS_ONE, resgid.real, GID_MINUS_ONE).unwrap();
    if getresgid().unwrap()
        != (ResGid {
            real: resgid.real,
            effective: resgid.real,
            saved: resgid.saved,
        })
    {
        panic!("setresgid exceeded, but did not de-escalate");
    }

    // De-escalate user first
    setresuid(UID_MINUS_ONE, resuid.real, UID_MINUS_ONE).unwrap();
    if getresuid().unwrap()
        != (ResUid {
            real: resuid.real,
            effective: resuid.real,
            saved: resuid.saved,
        })
    {
        panic!("setresuid exceeded, but did not de-escalate");
    }

    ret
}

pub fn permanently_drop_privileges() {
    use nix::unistd::*;

    // Drop group first
    let resgid = getresgid().unwrap();
    setresgid(resgid.real, resgid.real, resgid.real).unwrap();
    if getresgid().unwrap()
        != (ResGid {
            real: resgid.real,
            effective: resgid.real,
            saved: resgid.real,
        })
    {
        panic!("setresgid exceeded, but did not de-escalate");
    }
    // Drop user
    let resuid = getresuid().unwrap();
    setresuid(resuid.real, resuid.real, resuid.real).unwrap();
    if getresuid().unwrap()
        != (ResUid {
            real: resuid.real,
            effective: resuid.real,
            saved: resuid.real,
        })
    {
        panic!("setresuid exceeded, but did not de-escalate");
    }
}

pub fn verify_safe_to_run_as_root(path: &std::path::PathBuf) -> stacked_errors::Result<()> {
    use std::os::unix::fs::MetadataExt;
    if !path.exists() {
        return Err(anyhow!("{:?} does not exist; try building with Nix?", path));
    }
    let metadata = std::fs::metadata(path).map_err(stacked_errors::Error::from_err)?;
    if metadata.uid() != 0 || metadata.gid() != 0 || metadata.mode() & 0o002 != 0 {
        return Err(anyhow!("We will run {:?} as root, so it should be owned by root, root-group, and not world-writable", path));
    }
    Ok(())
}
