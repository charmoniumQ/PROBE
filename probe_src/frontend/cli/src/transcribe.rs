use std::{io::Write, path::Path};

use color_eyre::eyre::{Result, WrapErr};
use log::{debug, warn};

use crate::util::Dir;

pub fn transcribe<P: AsRef<Path>, T: Write>(
    record_dir: P,
    tar: &mut tar::Builder<T>,
) -> Result<()> {
    debug!("Starting transcription process");

    let log_dir = Dir::temp(true).wrap_err("Failed to create temp directory for transcription")?;
    debug!("Created temp directory for transcription: {:?}", log_dir.path());

    debug!("Parsing top-level record directory: {:?}", record_dir.as_ref());
    probe_frontend::transcribe::parse_top_level(record_dir, &log_dir)
        .wrap_err("Failed to transcribe record directory")?;

    debug!("Appending parsed directory to tarball");
    tar.append_dir_all(".", &log_dir)
        .wrap_err("Failed to copy output dir into archive")?;

    debug!("Finishing writing tarball");
    tar.finish().wrap_err("Failed to finish writing tarball")?;

    debug!("Transcription process completed successfully");
    Ok(())
}
