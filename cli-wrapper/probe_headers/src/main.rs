use eyre::{ContextCompat, Result, WrapErr};
use memory_parsing::{ByteString, SizedMemory, StringArray};

macro_rules! size_checks {
    ($($x:ty),+ $(,)?) => { vec![
        $(
            format!(
                "_Static_assert(sizeof({c_name}) == {size}, \"disagrees with Rust\");\n_Static_assert(_Alignof({c_name}) == {align}, \"disagrees with Rust\" );\n",
                c_name = <$x as SizedMemory>::c_name().expect(&format!("no c_name for {}", std::any::type_name::<$x>())),
                size = <$x as SizedMemory>::size(),
                align = <$x as SizedMemory>::align(),
            )
        ),+
    ] };
}

/* This wants to be a build-script, but it needs access to impls defined in this crate. */
fn main() -> Result<()> {
    let out_file = std::env::var_os("JSONSCHEMA_OUTFILE").wrap_err_with(|| "JSONSCHEMA_OUTFILE")?;
    let schema = schemars::schema_for!(probe_headers::All);
    let out_file_opened = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(out_file)
        .wrap_err("opening jsonschema file")?;
    serde_json::to_writer_pretty(out_file_opened, &schema).wrap_err("writing jsonschema file")?;

    let out_file = std::env::var_os("SIZE_CHECK_OUTFILE").wrap_err_with(|| "SIZE_CHECK_OUTFILE")?;
    let size_checks = size_checks!(
        bool,
        ByteString,
        Option::<ByteString>,
        StringArray,
        probe_headers::TimeVal,
        probe_headers::Rusage,
        probe_headers::StatxTimestamp,
        probe_headers::Path,
        probe_headers::InitExecEpochOp,
        probe_headers::InitThreadOp,
        probe_headers::OpenOp,
        probe_headers::CloseOp,
        probe_headers::ChdirOp,
        probe_headers::ExecOp,
        probe_headers::SpawnOp,
        probe_headers::ExitProcessOp,
        probe_headers::ExitThreadOp,
        probe_headers::AccessOp,
        probe_headers::StatResult,
        probe_headers::StatOp,
        probe_headers::ReaddirOp,
        probe_headers::WaitOp,
        probe_headers::Ownership,
        probe_headers::MetadataValue,
        probe_headers::Times,
        probe_headers::UpdateMetadataOp,
        probe_headers::ReadLinkOp,
        probe_headers::DupOp,
        probe_headers::HardLinkOp,
        probe_headers::SymbolicLinkOp,
        probe_headers::UnlinkOp,
        probe_headers::RenameOp,
        probe_headers::FileType,
        probe_headers::MkFileOp,
        probe_headers::OpData,
        probe_headers::Op,
    );
    let source = "#include <stdbool.h>\n#include \"./headers.h\"\n".to_owned()
        + &size_checks.clone().into_iter().collect::<String>();
    std::fs::write(&out_file, source).wrap_err("writing C size checks")?;

    Ok(())
}
