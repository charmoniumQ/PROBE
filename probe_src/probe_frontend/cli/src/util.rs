use std::{
    fs, io,
    path::{Path, PathBuf},
};

use color_eyre::eyre::{Context, Result};
use rand::Rng;

#[derive(Debug)]
pub struct Dir {
    path: PathBuf,
    pub drop: bool,
}

impl Dir {
    #[inline]
    pub fn new(path: PathBuf) -> Result<Self> {
        fs::create_dir(&path).wrap_err("Failed to create named directory")?;
        Ok(Self { path, drop: false })
    }

    pub fn temp(drop: bool) -> Result<Self> {
        let mut path = std::env::temp_dir();
        path.push(format!("probe-{}", rand_alphanumeric(8)));

        match fs::create_dir(&path) {
            Ok(_) => Ok(Self { path, drop }),
            Err(e) => match e.kind() {
                io::ErrorKind::AlreadyExists => Self::temp(drop),
                _ => Err(e).wrap_err("Failed to create temp directory"),
            },
        }
    }

    #[inline]
    pub fn path(&self) -> &Path {
        self.path.as_path()
    }
}

impl AsRef<Path> for Dir {
    fn as_ref(&self) -> &Path {
        self.path.as_path()
    }
}

impl Drop for Dir {
    fn drop(&mut self) {
        if self.drop {
            if let Err(e) = fs::remove_dir_all(&self.path) {
                log::warn!(
                    "Failed to remove temporary directory '{}' because: {}",
                    self.path.to_string_lossy(),
                    e
                );
            }
        }
    }
}

fn rand_alphanumeric(len: usize) -> String {
    const CHARSET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ\
                            abcdefghijklmnopqrstuvwxyz\
                            0123456789";

    let mut rng = rand::thread_rng();

    (0..len)
        .map(|_| {
            let idx = rng.gen_range(0..CHARSET.len());
            CHARSET[idx] as char
        })
        .collect()
}
