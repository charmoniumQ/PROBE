#[allow(unused_imports)]
pub use crate::ffi::{
    dev_t, gid_t, ino_t, mode_t, rusage, statx, statx_timestamp, timespec, timeval, uid_t, CloneOp,
    CloseOp, ExitOp, GetRUsageOp, InitProcessOp, InitThreadOp, WaitOp,
};
pub use std::ffi::{c_int, c_uint};

use color_eyre::eyre::{eyre, Context, Result};
use serde::{Deserialize, Serialize};
use std::ffi::{CStr, CString};

use crate::{arena::ArenaContext, ffi};

/// Specialized version of [`std::convert::From`] for working with libprobe arena structs.
///
/// Since [`ffi`] structs from arena allocator files have intrinsically invalid pointers (because
/// they came from a different virtual memory space). This trait and It's sibling [`FfiInto`]
/// exist to act as [`From`] and [`Into`] with an added parameter of a [`ArenaContext`] that can be
/// used to decode pointers.
pub(crate) trait FfiFrom<T> {
    fn ffi_from(value: &T, ctx: &ArenaContext) -> Result<Self>
    where
        Self: Sized;
}

/// Specialized version of [`std::convert::Into`] for working with libprobe arena structs.
///
/// Much like [`std::convert::Into`] this trait is implemented automatically with a blanket
/// implementation as the reciprocal of [`FfiFrom`].
pub(crate) trait FfiInto<T> {
    fn ffi_into(&self, ctx: &ArenaContext) -> Result<T>;
}

impl<T, U> FfiInto<U> for T
where
    U: FfiFrom<T>,
{
    #[inline]
    fn ffi_into(&self, ctx: &ArenaContext) -> Result<U> {
        U::ffi_from(self, ctx)
    }
}

/// Try to convert an invalid pointer from and ffi libprobe struct into a string type.
///
/// The strings emitted by libprobe are from C code, so they're pointers to an arbitrary sequence
/// of non-null bytes terminated by a null byte. This means we can't use the [`String`] type since
/// rust requires that all [`String`]s are valid UTF-8.
///
/// Instead we use [`CString`] which is provided by the standard library for ffi code like this.
fn try_to_cstring(str: *const i8, ctx: &ArenaContext) -> Result<CString> {
    if str.is_null() {
        CString::new("").wrap_err("Failed to create empty CString")
    } else {
        match ctx.try_get_slice(str as usize) {
            Some(x) => Ok(CStr::from_bytes_until_nul(x)
                .wrap_err("Failed to create CString")?
                .to_owned()),
            None => return Err(eyre!("Unable to lookup pointer {0:#x}", (str as usize))),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Path {
    pub dirfd_minus_at_fdcwd: i32,
    pub path: CString,
    pub device_major: dev_t,
    pub device_minor: dev_t,
    pub inode: ino_t,
    pub mtime: statx_timestamp,
    pub ctime: statx_timestamp,
    pub stat_valid: bool,
    pub dirfd_valid: bool,
}

impl FfiFrom<ffi::Path> for Path {
    fn ffi_from(value: &ffi::Path, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            dirfd_minus_at_fdcwd: value.dirfd_minus_at_fdcwd,
            path: try_to_cstring(value.path, ctx)
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
    pub program_name: CString,
}

impl FfiFrom<ffi::InitExecEpochOp> for InitExecEpochOp {
    fn ffi_from(value: &ffi::InitExecEpochOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            epoch: value.epoch,
            program_name: try_to_cstring(value.program_name, ctx)
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

impl FfiFrom<ffi::OpenOp> for OpenOp {
    fn ffi_from(value: &ffi::OpenOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.ffi_into(ctx)?,
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

impl FfiFrom<ffi::ChdirOp> for ChdirOp {
    fn ffi_from(value: &ffi::ChdirOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.ffi_into(ctx)?,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecOp {
    pub path: Path,
    pub ferrno: c_int,
}

impl FfiFrom<ffi::ExecOp> for ExecOp {
    fn ffi_from(value: &ffi::ExecOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.ffi_into(ctx)?,
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

impl FfiFrom<ffi::AccessOp> for AccessOp {
    fn ffi_from(value: &ffi::AccessOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.ffi_into(ctx)?,
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

impl FfiFrom<ffi::StatOp> for StatOp {
    fn ffi_from(value: &ffi::StatOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.ffi_into(ctx)?,
            flags: value.flags,
            statx_buf: value.statx_buf,
            ferrno: value.ferrno,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaddirOp {
    pub dir: Path,
    pub child: CString,
    pub all_children: bool,
    pub ferrno: c_int,
}

impl FfiFrom<ffi::ReaddirOp> for ReaddirOp {
    fn ffi_from(value: &ffi::ReaddirOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            dir: value.dir.ffi_into(ctx)?,
            child: try_to_cstring(value.child, ctx)
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
        log::debug!("[unsafe] decoding Metadata tagged union");
        Ok(match kind {
            ffi::MetadataKind_MetadataMode => Metadata::Mode(unsafe { value.mode }),
            ffi::MetadataKind_MetadataOwnership => Metadata::Ownership {
                uid: unsafe { value.ownership }.uid,
                gid: unsafe { value.ownership }.gid,
            },
            ffi::MetadataKind_MetadataTimes => Metadata::Times {
                is_null: unsafe { value.times }.is_null,
                atime: unsafe { value.times }.atime,
                mtime: unsafe { value.times }.mtime,
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

impl FfiFrom<ffi::UpdateMetadataOp> for UpdateMetadataOp {
    fn ffi_from(value: &ffi::UpdateMetadataOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.ffi_into(ctx)?,
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
    pub resolved: CString,
    pub ferrno: c_int,
}

impl FfiFrom<ffi::ReadLinkOp> for ReadLinkOp {
    fn ffi_from(value: &ffi::ReadLinkOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.ffi_into(ctx)?,
            resolved: try_to_cstring(value.resolved, ctx)
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
        log::debug!("[unsafe] decoding Op tagged union");
        Ok(match kind {
            ffi::OpCode_init_process_op_code => {
                Self::InitProcess(unsafe { value.init_process_epoch })
            }
            ffi::OpCode_init_exec_epoch_op_code => Self::InitExecEpoch(
                unsafe { value.init_exec_epoch }
                    .ffi_into(ctx)
                    .wrap_err("Unable to decode InitExecEpochOp")?,
            ),
            ffi::OpCode_init_thread_op_code => Self::InitThread(unsafe { value.init_thread }),
            ffi::OpCode_open_op_code => Self::Open(
                unsafe { value.open }
                    .ffi_into(ctx)
                    .wrap_err("Unable to decode OpenOp")?,
            ),
            ffi::OpCode_close_op_code => Self::Close(unsafe { value.close }),
            ffi::OpCode_chdir_op_code => Self::Chdir(
                unsafe { value.chdir }
                    .ffi_into(ctx)
                    .wrap_err("Unable to decode ChdirOp")?,
            ),
            ffi::OpCode_exec_op_code => Self::Exec(
                unsafe { value.exec }
                    .ffi_into(ctx)
                    .wrap_err("Unable to decode ExecOp")?,
            ),
            ffi::OpCode_clone_op_code => Self::Clone(unsafe { value.clone }),
            ffi::OpCode_exit_op_code => Self::Exit(unsafe { value.exit }),
            ffi::OpCode_access_op_code => Self::Access(
                unsafe { value.access }
                    .ffi_into(ctx)
                    .wrap_err("Unable to decode AccessOp")?,
            ),
            ffi::OpCode_stat_op_code => Self::Stat(
                unsafe { value.stat }
                    .ffi_into(ctx)
                    .wrap_err("Unable to decode StatOp")?,
            ),
            ffi::OpCode_readdir_op_code => Self::Readdir(
                unsafe { value.readdir }
                    .ffi_into(ctx)
                    .wrap_err("Unable to decode ReaddirOp")?,
            ),
            ffi::OpCode_wait_op_code => Self::Wait(unsafe { value.wait }),
            ffi::OpCode_getrusage_op_code => Self::GetRUsage(unsafe { value.getrusage }),
            ffi::OpCode_update_metadata_op_code => Self::UpdateMetadata(
                unsafe { value.update_metadata }
                    .ffi_into(ctx)
                    .wrap_err("Unable to decode UpdateMetadataOp")?,
            ),
            ffi::OpCode_read_link_op_code => Self::ReadLink(
                unsafe { value.read_link }
                    .ffi_into(ctx)
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

impl FfiFrom<ffi::Op> for Op {
    fn ffi_from(value: &ffi::Op, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            data: unsafe { OpInternal::from_kind_and_value(value.op_code, &value.data, ctx) }
                .wrap_err("Unable to decode Op tagged union")?,
            time: value.time,
        })
    }
}
