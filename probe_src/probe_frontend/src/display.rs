use std::fmt::Display;

use crate::ops;
use chrono::{DateTime, SecondsFormat};

impl Display for ops::statx_timestamp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match DateTime::from_timestamp(self.tv_sec, self.tv_nsec) {
            Some(x) => f.write_str(&x.to_rfc3339_opts(SecondsFormat::Secs, true)),
            None => f.write_str("[INVALID TIMESTAMP]"),
        }
    }
}

impl Display for ops::timeval {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match DateTime::from_timestamp(self.tv_sec, self.tv_usec as u32 * 1000) {
            Some(x) => f.write_str(&x.to_rfc3339_opts(SecondsFormat::Secs, true)),
            None => f.write_str("[INVALID TIMESTAMP]"),
        }
    }
}

impl Display for ops::statx {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ uid={}, gid={}, mode={:#06o} ino={}, size={}, mtime={} ]",
            self.stx_uid,
            self.stx_gid,
            self.stx_mode,
            self.stx_ino,
            self.stx_size,
            self.stx_mtime,
        )
    }
}

impl Display for ops::rusage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ utime={}, stime={}, maxrss={} ]",
            self.ru_utime,
            self.ru_stime,
            self.ru_maxrss,
        )
    }
}

impl Display for ops::Path {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ dirfd={}, path='{}', inode={}, mtime={} ]",
            self.dirfd_minus_at_fdcwd + libc::AT_FDCWD,
            self.path.to_string_lossy(),
            self.inode,
            self.mtime,
        )
    }
}

impl Display for ops::CloneOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ child_process_id={}, child_thread_id={}, errno={} ]",
            self.child_process_id,
            self.child_thread_id,
            self.ferrno,
        )
    }
}

impl Display for ops::CloseOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ low_fd={}, high_fd={}, errno={} ]",
            self.low_fd, self.high_fd, self.ferrno,
        )
    }
}

impl Display for ops::ExitOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ satus={}, run_atexit_handlers={} ]",
            self.status, self.run_atexit_handlers,
        )
    }
}

impl Display for ops::GetRUsageOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ waitpid_arg={}, getrusage_arg={}, usage={}, errno={} ]",
            self.waitpid_arg, self.getrusage_arg, self.usage, self.ferrno,
        )
    }
}

impl Display for ops::InitProcessOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[ pid={} ]", self.pid)
    }
}

impl Display for ops::InitThreadOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[ tid={} ]", self.tid)
    }
}

impl Display for ops::WaitOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ pid={}, options={}, status={}, ret={}, errno={} ]",
            self.pid, self.options, self.status, self.ret, self.ferrno,
        )
    }
}

impl Display for ops::InitExecEpochOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ epoch={}, program_name={} ]",
            self.epoch,
            self.program_name.to_string_lossy(),
        )
    }
}

impl Display for ops::OpenOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ path={}, flags={}, mode={:#06o} fd={}, errno={} ]",
            self.path, self.flags, self.mode, self.fd, self.ferrno,
        )
    }
}

impl Display for ops::ChdirOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[ path={}, errno={} ]", self.path, self.ferrno,)
    }
}

impl Display for ops::ExecOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[ path={}, errno={} ]", self.path, self.ferrno,)
    }
}

impl Display for ops::AccessOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ path={}, mode={:#06o}, flags={}, errno={} ]",
            self.path, self.mode, self.flags, self.ferrno,
        )
    }
}

impl Display for ops::StatOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ path={}, flags={}, statx_buf={}, errno={} ]",
            self.path, self.flags, self.statx_buf, self.ferrno,
        )
    }
}

impl Display for ops::ReaddirOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ dir={}, child='{}', all_children={}, errno={} ]",
            self.dir,
            self.child.to_string_lossy(),
            self.all_children,
            self.ferrno,
        )
    }
}

impl Display for ops::Metadata {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ops::Metadata::Mode(mode) => write!(f, "Mode[ mode={:#06o} ]", mode),
            ops::Metadata::Ownership { uid, gid } => {
                write!(f, "Ownership[ uid={}, gid={} ]", uid, gid)
            }
            ops::Metadata::Times {
                is_null,
                atime,
                mtime,
            } => write!(
                f,
                "Times[ is_null={}, atime={}, mtime={} ]",
                is_null, atime, mtime
            ),
        }
    }
}

impl Display for ops::UpdateMetadataOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ path={}, flags={}, metadata={}, errno={} ]",
            self.path, self.flags, self.metadata, self.ferrno,
        )
    }
}

impl Display for ops::ReadLinkOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[ path={}, resolved='{}', errno={} ]",
            self.path,
            self.resolved.to_string_lossy(),
            self.ferrno
        )
    }
}

impl Display for ops::OpInternal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        fn wfmt(f: &mut std::fmt::Formatter<'_>, x: &str, y: impl Display) -> std::fmt::Result {
            write!(f, "{}{}", x, y)
        }

        match self {
            ops::OpInternal::InitProcess(x) => wfmt(f, "InitProcessOp", x),
            ops::OpInternal::InitExecEpoch(x) => wfmt(f, "InitExecEpochOp", x),
            ops::OpInternal::InitThread(x) => wfmt(f, "InitThreadOp", x),
            ops::OpInternal::Open(x) => wfmt(f, "OpenOp", x),
            ops::OpInternal::Close(x) => wfmt(f, "CloseOp", x),
            ops::OpInternal::Chdir(x) => wfmt(f, "ChdirOp", x),
            ops::OpInternal::Exec(x) => wfmt(f, "ExecOp", x),
            ops::OpInternal::Clone(x) => wfmt(f, "CloneOp", x),
            ops::OpInternal::Exit(x) => wfmt(f, "ExitOp", x),
            ops::OpInternal::Access(x) => wfmt(f, "AccessOp", x),
            ops::OpInternal::Stat(x) => wfmt(f, "StatOp", x),
            ops::OpInternal::Readdir(x) => wfmt(f, "ReadirOp", x),
            ops::OpInternal::Wait(x) => wfmt(f, "WaitOp", x),
            ops::OpInternal::GetRUsage(x) => wfmt(f, "GetRUsageOp", x),
            ops::OpInternal::UpdateMetadata(x) => wfmt(f, "UpdateMetadataOp", x),
            ops::OpInternal::ReadLink(x) => wfmt(f, "ReadLinkOp", x),
        }
    }
}

impl Display for ops::Op {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.data.fmt(f)
    }
}
