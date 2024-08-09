#![allow(non_upper_case_globals)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]

use crate::error::{ProbeError, Result};
use crate::transcribe::ArenaContext;
use probe_macros::{MakeRustOp, PygenDataclass};
use serde::{Deserialize, Serialize};
use std::ffi::CString;
use std::vec::Vec;

/// Specialized version of [`std::convert::From`] for working with libprobe arena structs.
///
/// Since `C_*` structs from arena allocator files have intrinsically invalid pointers (because
/// they came from a different virtual memory space). This trait and It's sibling [`FfiInto`]
/// exist to act as [`From`] and [`Into`] with an added parameter of a [`ArenaContext`] that can be
/// used to decode pointers.
///
/// The autogenerated, rust versions of `C_*` structs implement this trait by recursively calling it
/// on each of it's fields. In order to make this work there are three base case implementations:
///
/// - `*mut i8` and `*const i8` can (try to) be converted to [`CString`]s by looking up the
///   pointers in the [`ArenaContext`],
/// - Any type implementing [`Copy`], this base case just returns itself.
pub trait FfiFrom<T> {
    fn ffi_from(value: &T, ctx: &ArenaContext) -> Result<Self>
    where
        Self: Sized;
}

impl<T: Copy> FfiFrom<T> for T {
    #[inline]
    fn ffi_from(value: &T, _: &ArenaContext) -> Result<Self> {
        Ok(*value)
    }
}
impl FfiFrom<*const i8> for CString {
    #[inline]
    fn ffi_from(value: &*const i8, ctx: &ArenaContext) -> Result<Self> {
        try_cstring(*value, ctx)
    }
}
impl FfiFrom<*mut i8> for CString {
    #[inline]
    fn ffi_from(value: &*mut i8, ctx: &ArenaContext) -> Result<Self> {
        try_cstring(*value, ctx)
    }
}

/// Specialized version of [`std::convert::Into`] for working with libprobe arena structs.
///
/// Much like [`std::convert::Into`] this trait is implemented automatically with a blanket
/// implementation as the reciprocal of [`FfiFrom`].
///
/// See [`FfiFrom`] for an explanation of how this is used in the conversion of `C_` structs
pub trait FfiInto<T> {
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

fn try_cstring(str: *const i8, ctx: &ArenaContext) -> Result<CString> {
    if str.is_null() {
        std::ffi::CString::new("").map_err(|_| ProbeError::MissingNull)
    } else {
        match ctx.try_get_slice(str as usize) {
            Some(x) => Ok(std::ffi::CStr::from_bytes_until_nul(x)
                .map_err(|_| ProbeError::MissingNull)?
                .to_owned()),
            None => Err(ProbeError::InvalidPointer(str as usize)),
        }
    }
}

// Bindings are generated by `../build.sh` and the MakeRustOp proc-macro
include!(concat!(env!("OUT_DIR"), "/bindings.rs"));

// NOTE: the raw versions of these Ops are tagged unions, so currently they have to be manually
// implemented, this is somewhat confusing since they extensively use types and trait
// implementations that are auto-generated.

#[derive(Debug, Clone, Serialize, Deserialize, PygenDataclass)]
pub enum Metadata {
    #[serde(untagged)]
    Mode {
        mode: mode_t,

        #[serde(serialize_with = "Metadata::serialize_variant_mode")]
        #[serde(skip_deserializing)]
        _type: (),
    },
    #[serde(untagged)]
    Ownership {
        uid: uid_t,
        gid: gid_t,

        #[serde(serialize_with = "Metadata::serialize_variant_ownership")]
        #[serde(skip_deserializing)]
        _type: (),
    },
    #[serde(untagged)]
    Times {
        is_null: bool,
        atime: Timeval,
        mtime: Timeval,

        #[serde(serialize_with = "Metadata::serialize_variant_times")]
        #[serde(skip_deserializing)]
        _type: (),
    },
}

impl Metadata {
    fn serialize_variant_mode<S: serde::Serializer>(
        _: &(),
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serializer.serialize_str("Mode")
    }
    fn serialize_variant_ownership<S: serde::Serializer>(
        _: &(),
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serializer.serialize_str("Ownership")
    }
    fn serialize_variant_times<S: serde::Serializer>(
        _: &(),
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serializer.serialize_str("Times")
    }
}

impl FfiFrom<C_UpdateMetadataOp> for Metadata {
    fn ffi_from(value: &C_UpdateMetadataOp, ctx: &ArenaContext) -> Result<Self> {
        let kind = value.kind;
        let value = value.value;

        log::debug!("[unsafe] decoding Metadata tagged union");
        Ok(match kind {
            C_MetadataKind_MetadataMode => Metadata::Mode {
                mode: unsafe { value.mode },

                _type: (),
            },
            C_MetadataKind_MetadataOwnership => Metadata::Ownership {
                uid: unsafe { value.ownership }.uid,
                gid: unsafe { value.ownership }.gid,

                _type: (),
            },
            C_MetadataKind_MetadataTimes => Metadata::Times {
                is_null: unsafe { value.times }.is_null,
                atime: unsafe { value.times }.atime.ffi_into(ctx)?,
                mtime: unsafe { value.times }.mtime.ffi_into(ctx)?,

                _type: (),
            },
            _ => return Err(ProbeError::InvalidVariant(kind)),
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PygenDataclass)]
pub struct UpdateMetadataOp {
    pub path: Path,
    pub flags: ::std::os::raw::c_int,
    pub metadata: Metadata,
    pub ferrno: ::std::os::raw::c_int,

    #[serde(serialize_with = "UpdateMetadataOp::serialize_type")]
    #[serde(skip_deserializing)]
    pub _type: (),
}

impl UpdateMetadataOp {
    fn serialize_type<S: serde::Serializer>(
        _: &(),
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serializer.serialize_str("UpdateMetadataOp")
    }
}

impl FfiFrom<C_UpdateMetadataOp> for UpdateMetadataOp {
    fn ffi_from(value: &C_UpdateMetadataOp, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            path: value.path.ffi_into(ctx)?,
            flags: value.flags,
            metadata: value
                .ffi_into(ctx)
                .map_err(|e| ProbeError::FFiConversionError {
                    msg: "Unable to decode Metadata",
                    inner: Box::new(e),
                })?,
            ferrno: value.ferrno,

            _type: (),
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PygenDataclass)]
pub enum OpInternal {
    #[serde(untagged)]
    InitProcessOp(InitProcessOp),
    #[serde(untagged)]
    InitExecEpochOp(InitExecEpochOp),
    #[serde(untagged)]
    InitThreadOp(InitThreadOp),
    #[serde(untagged)]
    OpenOp(OpenOp),
    #[serde(untagged)]
    CloseOp(CloseOp),
    #[serde(untagged)]
    ChdirOp(ChdirOp),
    #[serde(untagged)]
    ExecOp(ExecOp),
    #[serde(untagged)]
    CloneOp(CloneOp),
    #[serde(untagged)]
    ExitOp(ExitOp),
    #[serde(untagged)]
    AccessOp(AccessOp),
    #[serde(untagged)]
    StatOp(StatOp),
    #[serde(untagged)]
    ReaddirOp(ReaddirOp),
    #[serde(untagged)]
    WaitOp(WaitOp),
    #[serde(untagged)]
    GetRUsageOp(GetRUsageOp),
    #[serde(untagged)]
    UpdateMetadataOp(UpdateMetadataOp),
    #[serde(untagged)]
    ReadLinkOp(ReadLinkOp),
}

impl FfiFrom<C_Op> for OpInternal {
    fn ffi_from(value: &C_Op, ctx: &ArenaContext) -> Result<Self> {
        let kind = value.op_code;
        let value = value.data;

        log::debug!("[unsafe] decoding Op tagged union [ OpCode={} ]", kind);
        Ok(match kind {
            C_OpCode_init_process_op_code => {
                Self::InitProcessOp(unsafe { value.init_process }.ffi_into(ctx)?)
            }
            C_OpCode_init_exec_epoch_op_code => {
                Self::InitExecEpochOp(unsafe { value.init_exec_epoch }.ffi_into(ctx)?)
            }
            C_OpCode_init_thread_op_code => {
                Self::InitThreadOp(unsafe { value.init_thread }.ffi_into(ctx)?)
            }
            C_OpCode_open_op_code => Self::OpenOp(unsafe { value.open }.ffi_into(ctx)?),
            C_OpCode_close_op_code => Self::CloseOp(unsafe { value.close }.ffi_into(ctx)?),
            C_OpCode_chdir_op_code => Self::ChdirOp(unsafe { value.chdir }.ffi_into(ctx)?),
            C_OpCode_exec_op_code => Self::ExecOp(unsafe { value.exec }.ffi_into(ctx)?),
            C_OpCode_clone_op_code => Self::CloneOp(unsafe { value.clone }.ffi_into(ctx)?),
            C_OpCode_exit_op_code => Self::ExitOp(unsafe { value.exit }.ffi_into(ctx)?),
            C_OpCode_access_op_code => Self::AccessOp(unsafe { value.access }.ffi_into(ctx)?),
            C_OpCode_stat_op_code => Self::StatOp(unsafe { value.stat }.ffi_into(ctx)?),
            C_OpCode_readdir_op_code => Self::ReaddirOp(unsafe { value.readdir }.ffi_into(ctx)?),
            C_OpCode_wait_op_code => Self::WaitOp(unsafe { value.wait }.ffi_into(ctx)?),
            C_OpCode_getrusage_op_code => {
                Self::GetRUsageOp(unsafe { value.getrusage }.ffi_into(ctx)?)
            }
            C_OpCode_update_metadata_op_code => {
                Self::UpdateMetadataOp(unsafe { value.update_metadata }.ffi_into(ctx)?)
            }
            C_OpCode_read_link_op_code => {
                Self::ReadLinkOp(unsafe { value.read_link }.ffi_into(ctx)?)
            }
            _ => return Err(ProbeError::InvalidVariant(kind)),
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PygenDataclass)]
pub struct Op {
    pub data: OpInternal,
    pub time: Timespec,
    pub pthread_id: pthread_t,
    pub iso_c_thread_id: thrd_t,

    #[serde(serialize_with = "Op::serialize_type")]
    #[serde(skip_deserializing)]
    pub _type: (),
}

impl Op {
    fn serialize_type<S: serde::Serializer>(
        _: &(),
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serializer.serialize_str("Op")
    }
}

impl FfiFrom<C_Op> for Op {
    fn ffi_from(value: &C_Op, ctx: &ArenaContext) -> Result<Self> {
        Ok(Self {
            data: value.ffi_into(ctx)?,
            time: value.time.ffi_into(ctx)?,
            pthread_id: value.pthread_id,
            iso_c_thread_id: value.iso_c_thread_id,

            _type: (),
        })
    }
}

probe_macros::pygen_add_preamble!(
    "# https://github.com/torvalds/linux/blob/\
    73e931504f8e0d42978bfcda37b323dbbd1afc08/include/uapi/linux/fcntl.h#L98",
    "AT_FDCWD: int = -100"
);

probe_macros::pygen_add_prop!(Path impl dirfd -> int:
    "return self.dirfd_minus_at_fdcwd + AT_FDCWD"
);

// WARNING: this macro invocation must come after all other pygen calls for those calls to be
// included in the written file
probe_macros::pygen_write_to_env!("PYGEN_OUTFILE");

#[cfg(test)]
mod tests {
    // use super::*;

    // we define this constant in the generated python code, so we should make sure we get it
    // right.
    #[test]
    fn at_fdcwd_sanity_check() {
        assert_eq!(libc::AT_FDCWD, -100);
    }

    // since we're defining a custom version of the rusage struct (indirectly through rust-bindgen)
    // we should at least check that they're the same size.
    // FIXME: muslc has a different sized rusage struct so libc::rusage doesn't match
    // #[test]
    // fn rusage_size() {
    //     assert_eq!(
    //         std::mem::size_of::<libc::rusage>(),
    //         std::mem::size_of::<C_rusage>()
    //     );
    // }
}
