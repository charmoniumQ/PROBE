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
        probe_headers::PathArg,
        probe_headers::Inode,
        probe_headers::InitExecEpoch,
        probe_headers::InitThread,
        probe_headers::Open,
        probe_headers::Close,
        probe_headers::Exec,
        probe_headers::Spawn,
        probe_headers::ExitProcess,
        probe_headers::ExitThread,
        probe_headers::Access,
        probe_headers::StatResult,
        probe_headers::Stat,
        probe_headers::Readdir,
        probe_headers::Wait,
        probe_headers::Ownership,
        probe_headers::MetadataValue,
        probe_headers::Times,
        probe_headers::UpdateMetadata,
        probe_headers::ReadLink,
        probe_headers::Dup,
        probe_headers::HardLink,
        probe_headers::SymbolicLink,
        probe_headers::Unlink,
        probe_headers::Rename,
        probe_headers::OpData,
        probe_headers::Op,
    );
    let source = "#include <stdbool.h>\n#include \"./headers.h\"\n".to_owned()
        + &size_checks.clone().into_iter().collect::<String>();
    std::fs::write(&out_file, source).wrap_err("writing C size checks")?;

    Ok(())
}
