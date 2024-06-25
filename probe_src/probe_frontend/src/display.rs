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
        write!(f,
            "[ mask={}, blksize={}, attributes={}, nlink={}, uid={}, gid={}, \
            mode={:#06o} ino={}, size={}, blocks={}, attributes_mask={}, \
            atime={}, btime={}, ctime={}, mtime={}, rdev_major={}, \
            rdev_minor={}, dev_major={}, dev_minor={}, mnt_id={}, \
            dio_mem_align={}, dio_offset_align={} ]",
            self.stx_mask,
            self.stx_blksize,
            self.stx_attributes,
            self.stx_nlink,
            self.stx_uid,
            self.stx_gid,
            self.stx_mode,
            self.stx_ino,
            self.stx_size,
            self.stx_blocks,
            self.stx_attributes_mask,
            self.stx_atime,
            self.stx_btime,
            self.stx_ctime,
            self.stx_mtime,
            self.stx_rdev_major,
            self.stx_rdev_minor,
            self.stx_dev_major,
            self.stx_dev_minor,
            self.stx_mnt_id,
            self.stx_dio_mem_align,
            self.stx_dio_offset_align,
        )
    }
}

impl Display for ops::rusage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ utime={}, stime={}, maxrss={}, ixrss={}, idrss={}, isrss={}, \
            minflt={}, majflt={}, nswap={}, inblock={}, oublock={}, msgsnd={}, \
            msgrcv={}, nsignals={}, nvcsw={}, nivcsw={} ]",
            self.ru_utime,
            self.ru_stime,
            self.ru_maxrss,
            self.ru_ixrss,
            self.ru_idrss,
            self.ru_isrss,
            self.ru_minflt,
            self.ru_majflt,
            self.ru_nswap,
            self.ru_inblock,
            self.ru_oublock,
            self.ru_msgsnd,
            self.ru_msgrcv,
            self.ru_nsignals,
            self.ru_nvcsw,
            self.ru_nivcsw,
        )
    }
}

impl Display for ops::Path {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ dirfd_minus_at_fdcwd={}, path='{}', device_major={}, \
            device_minor={}, inode={}, mtime={}, ctime={}, stat_valid={}, \
            dirfd_valid={} ]",
            self.dirfd_minus_at_fdcwd,
            self.path.to_string_lossy(),
            self.device_major,
            self.device_minor,
            self.inode,
            self.mtime,
            self.ctime,
            self.stat_valid,
            self.dirfd_valid,
        )
    }
}

impl Display for ops::CloneOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ flags={}, run_pthread_atfork_handlers={}, child_process_id={}, \
            child_thread_id={}, ferrno={} ]",
            self.flags,
            self.run_pthread_atfork_handlers,
            self.child_process_id,
            self.child_thread_id,
            self.ferrno,
        )
    }
}

impl Display for ops::CloseOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ low_fd={}, high_fd={}, ferrno={} ]",
            self.low_fd, self.high_fd, self.ferrno,
        )
    }
}

impl Display for ops::ExitOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ satus={}, run_atexit_handlers={} ]",
            self.status, self.run_atexit_handlers,
        )
    }
}

impl Display for ops::GetRUsageOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ waitpid_arg={}, getrusage_arg={}, usage={}, ferrno={} ]",
            self.waitpid_arg, self.getrusage_arg, self.usage, self.ferrno,
        )
    }
}

impl Display for ops::InitProcessOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,"[ pid={} ]", self.pid)
    }
}

impl Display for ops::InitThreadOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,"[ tid={} ]", self.tid)
    }
}

impl Display for ops::WaitOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ pid={}, options={}, status={}, ret={}, ferrno={} ]",
            self.pid, self.options, self.status, self.ret, self.ferrno,
        )
    }
}

impl Display for ops::InitExecEpochOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ epoch={}, program_name={} ]",
            self.epoch,
            self.program_name.to_string_lossy(),
        )
    }
}

impl Display for ops::OpenOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ path={}, flags={}, mode={:#06o} fd={}, ferrno={} ]",
            self.path, self.flags, self.mode, self.fd, self.ferrno,
        )
    }
}

impl Display for ops::ChdirOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ path={}, ferrno={} ]",
            self.path, self.ferrno,
        )
    }
}

impl Display for ops::ExecOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ path={}, ferrno={} ]",
            self.path, self.ferrno,
        )
    }
}

impl Display for ops::AccessOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ path={}, mode={:#06o}, flags={}, ferrno={} ]",
            self.path, self.mode, self.flags, self.ferrno,
        )
    }
}

impl Display for ops::StatOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ path={}, flags={}, statx_buf={}, ferrno={} ]",
            self.path, self.flags, self.statx_buf, self.ferrno,
        )
    }
}

impl Display for ops::ReaddirOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ dir={}, child='{}', all_children={}, ferrno={} ]",
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
            ops::Metadata::Mode(mode) => write!(f,"Mode[ mode={:#06o} ]", mode),
            ops::Metadata::Ownership { uid, gid } => {
                write!(f,"Ownership[ uid={}, gid={} ]", uid, gid)
            }
            ops::Metadata::Times {
                is_null,
                atime,
                mtime,
            } => write!(f,
                "Times[ is_null={}, atime={}, mtime={} ]",
                is_null, atime, mtime
            ),
        }
    }
}

impl Display for ops::UpdateMetadataOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ path={}, flags={}, metadata={}, ferrno={} ]",
            self.path, self.flags, self.metadata, self.ferrno,
        )
    }
}

impl Display for ops::ReadLinkOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f,
            "[ path={}, resolved='{}', ferrno={} ]",
            self.path,
            self.resolved.to_string_lossy(),
            self.ferrno
        )
    }
}

impl Display for ops::OpInternal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        fn wfmt(f: &mut std::fmt::Formatter<'_>, x: &str, y: impl Display) -> std::fmt::Result {
            write!(f,"{}{}", x, y)
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
