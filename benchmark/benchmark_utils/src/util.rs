use stacked_errors::{anyhow, Error, Result, StackableErr};
use std::io::{Read, Write};

pub fn eprintln_error<T>(result: Result<T>) -> Option<T> {
    match result {
        Ok(val) => Some(val),
        Err(err) => {
            eprintln!("Non-fatal error: {:?}", err);
            None
        }
    }
}

pub fn write_to_file(path_str: String, content: String) -> Result<()> {
    let path = std::path::PathBuf::from(path_str);
    if path.exists() {
        let is_already_written = {
            let mut file = std::fs::OpenOptions::new()
                .read(true)
                .open(path.clone())
                .map_err(Error::from_err)
                .stack()?;
            let mut buffer = vec![0; content.len()];
            let read_bytes = file
                .read(&mut buffer[..])
                .map_err(Error::from_err)
                .stack()?;
            read_bytes == buffer.len() && buffer == content.as_bytes()
        };
        if !is_already_written {
            let mut file = std::fs::OpenOptions::new()
                .write(true)
                .open(path)
                .map_err(Error::from_err)
                .stack()?;
            file.write_all(content.as_bytes())
                .map_err(Error::from_err)
                .stack()?;
            //file.sync_all().map_err(Error::from_err).stack()?;
        }
        Ok(())
    } else {
        Err(anyhow!("File {:?} does not exist", path))
    }
}

pub fn write_to_file2(path: &std::path::Path, content: String) -> Result<()> {
    if path.exists() {
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .open(path)
            .map_err(Error::from_err)
            .context(anyhow!("{:?}", path))
            .stack()?;
        file.write_all(content.as_bytes())
            .map_err(Error::from_err)
            .context(anyhow!("{:?}", path))
            .stack()?;
        // file.sync_all().map_err(Error::from_err).stack()?;
        Ok(())
    } else {
        Err(anyhow!("File {:?} does not exist", path))
    }
}

pub fn check_cmd(mut cmd: std::process::Command, silence: bool) -> Result<()> {
    if !cmd
        .stdout(if silence {
            std::process::Stdio::piped()
        } else {
            std::process::Stdio::inherit()
        })
        .status()
        .map_err(Error::from_err)
        .context(anyhow!("Error launching {:?}", cmd))?
        .success()
    {
        Err(anyhow!("Command failed: {:?}", cmd))
    } else {
        Ok(())
    }
}
