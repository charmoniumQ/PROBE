#[allow(unused_imports)]
pub use crate::ffi::{
    dev_t, gid_t, ino_t, mode_t, rusage, statx, statx_timestamp, timespec, timeval, uid_t, CloneOp,
    CloseOp, ExitOp, GetRUsageOp, InitProcessOp, InitThreadOp, WaitOp,
};
use color_eyre::eyre::{eyre, Context};
pub use std::ffi::{c_int, c_uint};

use color_eyre::eyre::Result;
use serde::{Deserialize, Serialize};
use std::{
    ffi::{OsStr, OsString},
    os::unix::ffi::OsStrExt,
    slice,
};

use crate::{arena::ArenaContext, ffi};

pub(crate) trait DecodeFfi<T> {
    fn decode(value: &T, ctx: &ArenaContext) -> Result<Self>
    where
        Self: Sized;
}

pub(crate) trait ConvertFfi<T> {
    fn convert(&self, ctx: &ArenaContext) -> Result<T>;
}

impl<T, U> ConvertFfi<U> for T
where
    U: DecodeFfi<T>,
{
    #[inline]
    fn convert(&self, ctx: &ArenaContext) -> Result<U> {
        U::decode(self, ctx)
    }
}

fn try_to_osstring(str: *const i8, ctx: &ArenaContext) -> Result<OsString> {
    Ok(if str.is_null() {
        OsString::new()
    } else {
        match ctx.try_deref(str as usize) {
            Some(x) => {
                OsStr::from_bytes(unsafe { slice::from_raw_parts(x, libc::strlen(x as *const i8)) })
                    .to_os_string()
            }
            None => return Err(eyre!("Unable to lookup pointer {0:#x}", (str as usize))),
        }
    })
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Path {
    pub dirfd_minus_at_fdcwd: i32,
    pub path: OsString,
    pub device_major: dev_t,
    pub device_minor: dev_t,
    pub inode: ino_t,
    pub mtime: statx_timestamp,
    pub ctime: statx_timestamp,
    pub stat_valid: bool,
    pub dirfd_valid: bool,
}

impl DecodeFfi<ffi::Path> for Path {
    fn decode(value: &ffi::Path, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            dirfd_minus_at_fdcwd: value.dirfd_minus_at_fdcwd,
            path: try_to_osstring(value.path, ctx)
                .wrap_err("Unable to decode char* into path string")?,
            device_major: value.device_major,
            device_minor: value.device_minor,
            inode: value.inode,
            mtime: value.mtime,
            ctime: value.ctime,
            stat_valid: value.stat_valid,
            dirfd_valid: value.dirfd_valid,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InitExecEpochOp {
    pub epoch: c_uint,
    pub program_name: OsString,
}

impl DecodeFfi<ffi::InitExecEpochOp> for InitExecEpochOp {
    fn decode(value: &ffi::InitExecEpochOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            epoch: value.epoch,
            program_name: try_to_osstring(value.program_name, ctx)
                .wrap_err("Unable to decode program name char* into string")?,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpenOp {
    pub path: Path,
    pub flags: c_int,
    pub mode: mode_t,
    pub fd: i32,
    pub ferrno: c_int,
}

impl DecodeFfi<ffi::OpenOp> for OpenOp {
    fn decode(value: &ffi::OpenOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.convert(ctx)?,
            flags: value.flags,
            mode: value.mode,
            fd: value.fd,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChdirOp {
    pub path: Path,
    pub ferrno: c_int,
}

impl DecodeFfi<ffi::ChdirOp> for ChdirOp {
    fn decode(value: &ffi::ChdirOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.convert(ctx)?,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecOp {
    pub path: Path,
    pub ferrno: c_int,
}

impl DecodeFfi<ffi::ExecOp> for ExecOp {
    fn decode(value: &ffi::ExecOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.convert(ctx)?,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccessOp {
    pub path: Path,
    pub mode: c_int,
    pub flags: c_int,
    pub ferrno: c_int,
}

impl DecodeFfi<ffi::AccessOp> for AccessOp {
    fn decode(value: &ffi::AccessOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.convert(ctx)?,
            mode: value.mode,
            flags: value.flags,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatOp {
    pub path: Path,
    pub flags: c_int,
    pub statx_buf: statx,
    pub ferrno: c_int,
}

impl DecodeFfi<ffi::StatOp> for StatOp {
    fn decode(value: &ffi::StatOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.convert(ctx)?,
            flags: value.flags,
            statx_buf: value.statx_buf,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaddirOp {
    pub dir: Path,
    pub child: OsString,
    pub all_children: bool,
    pub ferrno: c_int,
}

impl DecodeFfi<ffi::ReaddirOp> for ReaddirOp {
    fn decode(value: &ffi::ReaddirOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            dir: value.dir.convert(ctx)?,
            child: try_to_osstring(value.child, ctx)
                .wrap_err("Unable to decode child char* into string")?,
            all_children: value.all_children,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Metadata {
    Mode(mode_t),
    Ownership {
        uid: uid_t,
        gid: gid_t,
    },
    Times {
        is_null: bool,
        atime: timeval,
        mtime: timeval,
    },
}

/// # safety
/// the [[`ffi::MetadataKind`]] passed to this function must a valid variant of MetadataKind enum
/// and be accurate for the passed value because it directly effects the interpretation of the
/// [[`ffi::MetadataValue`]] union with no additional checks
impl Metadata {
    pub unsafe fn from_kind_and_value(
        kind: ffi::MetadataKind,
        value: ffi::MetadataValue,
    ) -> Result<Self> {
        Ok(match kind {
            ffi::MetadataKind_MetadataMode => Metadata::Mode(value.mode),
            ffi::MetadataKind_MetadataOwnership => Metadata::Ownership {
                uid: value.ownership.uid,
                gid: value.ownership.gid,
            },
            ffi::MetadataKind_MetadataTimes => Metadata::Times {
                is_null: value.times.is_null,
                atime: value.times.atime,
                mtime: value.times.mtime,
            },
            _ => return Err(eyre!("Invalid MetadataKind Variant")),
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateMetadataOp {
    pub path: Path,
    pub flags: c_int,
    pub metadata: Metadata,
    pub ferrno: c_int,
}

impl DecodeFfi<ffi::UpdateMetadataOp> for UpdateMetadataOp {
    fn decode(value: &ffi::UpdateMetadataOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.convert(ctx)?,
            flags: value.flags,
            metadata: unsafe { Metadata::from_kind_and_value(value.kind, value.value) }
                .wrap_err("Unable to decode Metadata tagged union")?,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReadLinkOp {
    pub path: Path,
    pub resolved: OsString,
    pub ferrno: c_int,
}

impl DecodeFfi<ffi::ReadLinkOp> for ReadLinkOp {
    fn decode(value: &ffi::ReadLinkOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.convert(ctx)?,
            resolved: try_to_osstring(value.resolved, ctx)
                .wrap_err("Unable to decode symlink resolve char* to string")?,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OpInternal {
    InitProcess(InitProcessOp),
    InitExecEpoch(InitExecEpochOp),
    InitThread(InitThreadOp),
    Open(OpenOp),
    Close(CloseOp),
    Chdir(ChdirOp),
    Exec(ExecOp),
    Clone(CloneOp),
    Exit(ExitOp),
    Access(AccessOp),
    Stat(StatOp),
    Readdir(ReaddirOp),
    Wait(WaitOp),
    GetRUsage(GetRUsageOp),
    UpdateMetadata(UpdateMetadataOp),
    ReadLink(ReadLinkOp),
}

/// # safety
/// the [[`ffi::OpCode`]] passed to this function must a valid variant of OpCode enum
/// and be accurate for the passed value because it directly effects the interpretation of the
/// value union with no additional checks
impl OpInternal {
    pub unsafe fn from_kind_and_value(
        kind: ffi::OpCode,
        value: &ffi::Op__bindgen_ty_1,
        ctx: &ArenaContext,
    ) -> Result<Self> {
        Ok(match kind {
            ffi::OpCode_init_process_op_code => Self::InitProcess(value.init_process_epoch),
            ffi::OpCode_init_exec_epoch_op_code => Self::InitExecEpoch(
                value
                    .init_exec_epoch
                    .convert(ctx)
                    .wrap_err("Unable to decode InitExecEpochOp")?,
            ),
            ffi::OpCode_init_thread_op_code => Self::InitThread(value.init_thread),
            ffi::OpCode_open_op_code => Self::Open(
                value
                    .open
                    .convert(ctx)
                    .wrap_err("Unable to decode OpenOp")?,
            ),
            ffi::OpCode_close_op_code => Self::Close(value.close),
            ffi::OpCode_chdir_op_code => Self::Chdir(
                value
                    .chdir
                    .convert(ctx)
                    .wrap_err("Unable to decode ChdirOp")?,
            ),
            ffi::OpCode_exec_op_code => Self::Exec(
                value
                    .exec
                    .convert(ctx)
                    .wrap_err("Unable to decode ExecOp")?,
            ),
            ffi::OpCode_clone_op_code => Self::Clone(value.clone),
            ffi::OpCode_exit_op_code => Self::Exit(value.exit),
            ffi::OpCode_access_op_code => Self::Access(
                value
                    .access
                    .convert(ctx)
                    .wrap_err("Unable to decode AccessOp")?,
            ),
            ffi::OpCode_stat_op_code => Self::Stat(
                value
                    .stat
                    .convert(ctx)
                    .wrap_err("Unable to decode StatOp")?,
            ),
            ffi::OpCode_readdir_op_code => Self::Readdir(
                value
                    .readdir
                    .convert(ctx)
                    .wrap_err("Unable to decode ReaddirOp")?,
            ),
            ffi::OpCode_wait_op_code => Self::Wait(value.wait),
            ffi::OpCode_getrusage_op_code => Self::GetRUsage(value.getrusage),
            ffi::OpCode_update_metadata_op_code => Self::UpdateMetadata(
                value
                    .update_metadata
                    .convert(ctx)
                    .wrap_err("Unable to decode UpdateMetadataOp")?,
            ),
            ffi::OpCode_read_link_op_code => Self::ReadLink(
                value
                    .read_link
                    .convert(ctx)
                    .wrap_err("Unable to decode ReadlinkOp")?,
            ),
            _ => {
                if kind < ffi::OpCode_LAST_OP_CODE && kind > ffi::OpCode_FIRST_OP_CODE {
                    return Err(eyre!(
                        "Valid OpCode not handled (this is a bug, please report it)"
                    ));
                } else {
                    return Err(eyre!("Invalid OpCode"));
                }
            }
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Op {
    pub data: OpInternal,
    pub time: timespec,
}

impl DecodeFfi<ffi::Op> for Op {
    fn decode(value: &ffi::Op, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            data: unsafe { OpInternal::from_kind_and_value(value.op_code, &value.data, ctx) }
                .wrap_err("Unable to decode Op tagged union")?,
            time: value.time,
        })
    }
}
