use color_eyre::eyre::{eyre, Error, Result};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::str::FromStr;

lazy_static::lazy_static! {
    static ref NAME_EMAIL_REGEX: regex::Regex = regex::Regex::new(r"^(.*?)\s*\<(.*)\>\s*$").unwrap();
    static ref DPKG_QUERY_BIN: Option<PathBuf> = which::which("dpkg-query").ok();
    static ref RPM_BIN: Option<PathBuf> = which::which("rpm").ok();
}

#[derive(Debug, Clone)]
pub struct FileInfo {
    pub mime_type: String,
    pub git_root: Option<PathBuf>,
    pub deb_package: Option<String>,
    pub rpm_package: Option<String>,
    pub venv_path: Option<(PathBuf, PathBuf)>,
}

pub fn get_file_info<P: AsRef<Path>>(path: P) -> FileInfo {
    FileInfo {
        mime_type: get_mime_type(&path),
        git_root: get_git_root(&path),
        deb_package: get_deb_package_name(&path),
        rpm_package: get_rpm_package_name(&path),
        venv_path: find_venv_root(&path),
    }
}

pub fn get_mime_type<P: AsRef<Path>>(path: P) -> String {
    file_format::FileFormat::from_file(path)
        .map(|fmt| fmt.media_type().to_string())
        .unwrap_or_else(|_| "application/octet-stream".to_string())
}

pub fn get_git_root<P: AsRef<Path>>(path: P) -> Option<PathBuf> {
    let repo = gix::discover(path).ok()?;
    repo.workdir().map(|p| p.to_path_buf())
}

pub fn get_deb_package_name<P: AsRef<Path>>(path: P) -> Option<String> {
    let output = std::process::Command::new(DPKG_QUERY_BIN.clone()?)
        .arg("--search")
        .arg(path.as_ref().as_os_str())
        .output()
        .ok()?;
    Some(
        String::from_utf8(output.stdout)
            .unwrap()
            .split_once(':')
            .ok_or(eyre!("No colon"))
            .unwrap()
            .0
            .to_owned(),
    )
}

pub fn get_rpm_package_name<P: AsRef<Path>>(path: P) -> Option<String> {
    let output = std::process::Command::new(RPM_BIN.clone()?)
        .arg("--search")
        .arg(path.as_ref().as_os_str())
        .output()
        .ok()?;
    Some(String::from_utf8(output.stdout).unwrap())
}

fn find_venv_root<P: AsRef<Path>>(path: P) -> Option<(PathBuf, PathBuf)> {
    const SITE_PACKAGES: &str = "site-packages";
    const DIST_PACKAGES: &str = "dist-packages";
    let mut current = path.as_ref();
    let mut site_packages = None;
    while current.parent().is_some() {
        if current.file_name() == Some(SITE_PACKAGES.as_ref())
            || current.file_name() == Some(DIST_PACKAGES.as_ref())
        {
            site_packages = Some(current.to_path_buf());
        }
        if current.join("pyvenv.cfg").is_file() {
            let venv_root = current.to_path_buf();
            match site_packages {
                Some(site_packages) => return Some((venv_root, site_packages)),
                None => return None,
            }
        }
        current = current.parent().unwrap();
    }
    None
}

#[derive(Debug, Clone)]
pub struct NameEmail {
    pub name: String,
    pub email: Option<email_address::EmailAddress>,
}

fn get_email(name_email: &str) -> Option<(String, email_address::EmailAddress)> {
    let (name, part) = name_email.split_once('<')?;
    let (email_raw, _) = part.split_once('>')?;
    let email = email_address::EmailAddress::from_str(email_raw).ok()?;
    Some((name.trim().to_string(), email))
}

impl From<&str> for NameEmail {
    fn from(name_email: &str) -> NameEmail {
        if let Some((name, email)) = get_email(name_email) {
            NameEmail {name, email: Some(email)}
        } else {
            NameEmail {name: name_email.to_string(), email: None}
        }
    }
}

#[derive(Debug, Clone)]
pub struct DebPackageInfo {
    pub name: String,
    pub maintainer: NameEmail,
    pub version: String,
    pub original_maintainer: NameEmail,
}

impl TryFrom<&str> for DebPackageInfo {
    type Error = Error;
    fn try_from(package_name: &str) -> Result<DebPackageInfo> {
        let stdout = call_dpkg_query_status(package_name)
            .ok_or(eyre!("Could not call dpkg --query --status"))?;
        let fields = parse_rfc_822_headers(stdout.as_bytes())?;

        Ok(DebPackageInfo {
            name: get_one(&fields, "Package")?.to_string(),
            maintainer: NameEmail::from(get_one(&fields, "Maintainer")?.as_ref()),
            version: get_one(&fields, "Version")?.to_string(),
            original_maintainer: NameEmail::from(get_one(&fields, "Original-Maintainer")?.as_ref()),
        })
    }
}

#[cfg(not(test))]
fn call_dpkg_query_status(package_name: &str) -> Option<String> {
    let output =
        std::process::Command::new(DPKG_QUERY_BIN.clone().ok_or(eyre!("No dpkg_query")).ok()?)
            .arg("--status")
            .arg(package_name)
            .output()
            .ok()?;
    String::from_utf8(output.stdout).ok()
}

#[cfg(test)]
fn call_dpkg_query_status(package_name: &str) -> Option<String> {
    // podman run --rm ubuntu:latest dpkg-query --status coreutils-from-uutils
    Some("Package: coreutils-from-uutils
Protected: yes
Status: install ok installed
Priority: optional
Section: utils
Installed-Size: 237
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Architecture: all
Multi-Arch: foreign
Source: coreutils-from
Version: 0.0.0~ubuntu25
Replaces: coreutils (<< 9.5-1ubuntu2+0.0.0~ubuntu25), coreutils-from, libdigest-sha3-perl (<< 1.05-1ubuntu3~)
Provides: coreutils, coreutils-from
Pre-Depends: rust-coreutils (>> 0.1.0+git20250813), gnu-coreutils
Breaks: coreutils (<< 9.5-1ubuntu2+0.0.0~ubuntu25), libdigest-sha3-perl (<< 1.05-1ubuntu3~)
Conflicts: coreutils-from
Description: coreutils from the uutils project
 A Rust-based implementation of the coreutils, aiming at
 being a complete replacement.
Original-Maintainer: Julian Andres Klode <jak@debian.org>
".to_string())
}

#[derive(Debug, Clone)]
pub struct RpmPackageInfo {
    pub name: String,
    pub version: String,
    pub license: String,
    pub packager: NameEmail,
    pub vendor: String,
    pub homepage: url::Url,
}

#[cfg(not(test))]
fn call_rpm_info(name: &str) -> Option<String> {
    let output = std::process::Command::new(RPM_BIN.clone().ok_or(eyre!("No rpm")).ok()?)
        .arg("--query")
        .arg("--info")
        .arg(name)
        .output()
        .ok()?;
    String::from_utf8(output.stdout).ok()
}

#[cfg(test)]
fn call_rpm_info(name: &str) -> Option<String> {
    // podman run --rm ubuntu:latest dpkg-query --status coreutils-from-uutils
    Some("Name        : coreutils-single
Version     : 9.5
Release     : 7.el10
Architecture: x86_64
Install Date: Tue May 26 21:03:43 2026
Group       : Unspecified
Size        : 1403945
License     : GPL-3.0-or-later AND GFDL-1.3-no-invariants-or-later AND LGPL-2.1-or-later AND LGPL-3.0-or-later
Signature   :
              RSA/SHA256, Fri Mar  6 14:33:21 2026, Key ID dee5c11cc2a1e572
              RSA/SHA256, Fri Mar  6 14:33:22 2026, Key ID dee5c11cc2a1e572
Source RPM  : coreutils-9.5-7.el10.src.rpm
Build Date  : Thu Mar  5 09:49:27 2026
Build Host  : x64-builder03.almalinux.org
Packager    : AlmaLinux Packaging Team <packager@almalinux.org>
Vendor      : AlmaLinux
URL         : https://www.gnu.org/software/coreutils/
Summary     : coreutils multicall binary
Description :
These are the GNU core utilities,
packaged as a single multicall binary.
".to_string())
}

impl TryFrom<&str> for RpmPackageInfo {
    type Error = Error;
    fn try_from(name: &str) -> Result<RpmPackageInfo> {
        let stdout = call_rpm_info(name).ok_or(eyre!("Could not run rpm --info"))?;
        let fields = parse_colon_fields(&stdout);
        let url = get_one(&fields, "URL")?;
        Ok(RpmPackageInfo {
            name: get_one(&fields, "Name")?.to_string(),
            version: get_one(&fields, "Version")?.to_string(),
            license: get_one(&fields, "License")?.to_string(),
            packager: NameEmail::from(get_one(&fields, "Packager")?),
            vendor: get_one(&fields, "Vendor")?.to_string(),
            homepage: url::Url::parse(&url)?,
        })
    }
}

#[derive(Debug, Clone)]
pub struct PythonSitePackages {
    pub packages: Vec<PythonPackage>,
}

#[derive(Debug, Clone)]
pub struct PythonPackage {
    pub name: String,
    pub version: String,
    pub authors: Vec<NameEmail>,
    pub maintainers: Vec<NameEmail>,
    pub license: String,
    pub urls: HashMap<String, url::Url>,
    pub files: Vec<PathBuf>,
}

#[cfg(not(test))]
fn list_site_packages_dir<P: AsRef<Path>>(dir: P) -> Result<Vec<PathBuf>> {
    std::fs::read_dir(dir)?
        .map(|entry| Ok(entry?.path()))
        .collect::<Result<Vec<_>>>()
}

#[cfg(test)]
fn list_site_packages_dir<P: AsRef<Path>>(dir: P) -> Result<Vec<PathBuf>> {
    Ok(vec![dir.as_ref().join("numpy-2.4.6.dist-info")])
}

#[cfg(not(test))]
fn read_metadata_file<P: AsRef<Path>>(metadata_file: P) -> Result<Vec<u8>> {
    Ok(std::fs::read(metadata_file)?)
}

#[cfg(test)]
fn read_metadata_file<P: AsRef<Path>>(metadata_file: P) -> Result<Vec<u8>> {
    // cat ../../benchmark/simple-ml-pipeline/venv/lib/python3.14/site-packages/numpy-2.4.6.dist-info/METADATA
    Ok("Metadata-Version: 2.4
Name: numpy
Version: 2.4.6
Summary: Fundamental package for array computing in Python
Author: Travis E. Oliphant et al.
Maintainer-Email: NumPy Developers <numpy-discussion@python.org>
License-Expression: BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0
Project-URL: homepage, https://numpy.org
Project-URL: documentation, https://numpy.org/doc/
Project-URL: source, https://github.com/numpy/numpy
Project-URL: download, https://pypi.org/project/numpy/#files
Project-URL: tracker, https://github.com/numpy/numpy/issues
Project-URL: release notes, https://numpy.org/doc/stable/release
Requires-Python: >=3.11
Description-Content-Type: text/markdown

<h1 align=\"center\">
<img src=\"https://raw.githubusercontent.com/numpy/numpy/main/branding/logo/primary/numpylogo.svg\" width=\"300\">
</h1><br>
".as_bytes().to_vec())
}

#[cfg(not(test))]
fn read_owned_files<P: AsRef<Path>>(sources_file: P) -> Result<Vec<u8>> {
    Ok(std::fs::read(sources_file)?)
}

#[cfg(test)]
fn read_owned_files<P: AsRef<Path>>(sources_file: P) -> Result<Vec<u8>> {
    // head ../../benchmark/simple-ml-pipeline/venv/lib/python3.14/site-packages/numpy-2.4.6.dist-info/SOURCES.txt
    Ok("../../../bin/f2py,sha256=X445UH_Se8pg4O1pUfUNisQ9EaMcVK19zLdMRppkMyI,212
../../../bin/numpy-config,sha256=ChNV68iv83l7Ta5YQDKB0VwZB_jf_clW0JcVZBYYWck,212
numpy-2.4.6.dist-info/INSTALLER,sha256=zuuue4knoyJ-UwPPXg8fezS7VCrXJQrAP7zeNuwvFQg,4
numpy-2.4.6.dist-info/METADATA,sha256=sILFLMvjuIC64XfDUXG1LtbJR_OtceN2Lycj9gpBHeA,6608
numpy-2.4.6.dist-info/RECORD,,
numpy-2.4.6.dist-info/WHEEL,sha256=gnX4LgsyUzoruqAkC4ad72ARbfIwvCQlZYzHzJpjpK8,138
numpy-2.4.6.dist-info/entry_points.txt,sha256=7Cb63gyL2sIRpsHdADpl6xaIW5JTlUI-k_yqEVr0BSw,220
".as_bytes().to_vec())
}

impl PythonSitePackages {
    fn try_from<P: AsRef<Path>>(site_packages: P) -> Result<Vec<PythonPackage>> {
        let mut packages: Vec<PythonPackage> = vec![];
        for dir_name in list_site_packages_dir(&site_packages)? {
            let files = if dir_name.extension() == Some(std::ffi::OsStr::new("dist-info")) {
                Some((dir_name.join("METADATA"), dir_name.join("RECORD")))
            } else if dir_name.extension() == Some(std::ffi::OsStr::new("egg-info")) {
                Some((dir_name.join("PKG-INFO"), dir_name.join("SOURCES.txt")))
            } else {
                None
            };
            if let Some((metadata_file, owned_files)) = files {
                let metadata_bytes = read_metadata_file(&metadata_file)?;
                let owned_files_bytes = read_owned_files(owned_files)?;
                let headers = parse_rfc_822_email(&metadata_bytes[..])?;
                let urls = get_many(&headers, "Project-URL")
                        .iter()
                        .map(|string| {
                            let (left, right) = string.split_once(',').unwrap();
                            Ok((left.trim().to_string(), url::Url::parse(right)?))
                        })
                        .collect::<Result<Vec<_>>>()?
                        .into_iter()
                        .collect::<HashMap<_, _>>();
                let mut csv_reader = csv::ReaderBuilder::new()
                    .has_headers(false)
                    .from_reader(&owned_files_bytes[..]);
                let files = csv_reader
                        .records()
                        .map(|row| {
                            Ok(site_packages.as_ref().join(
                                row?.get(0)
                                    .ok_or(eyre!("Can not get 0th field"))?
                                    .to_string(),
                            ))
                        })
                        .collect::<Result<Vec<_>>>()?;
                packages.push(PythonPackage {
                    name: get_one(&headers, "Name")?.to_string(),
                    version: get_one(&headers, "Version")?.to_string(),
                    authors: get_many(&headers, "Author").iter().chain(
                        get_many(&headers, "Author-Email")
                            .iter()
                    )
                        .map(|s| NameEmail::from(s.as_str()))
                        .collect::<Vec<_>>(),
                    maintainers: get_many(&headers, "Maintainers").iter().chain(
                        get_many(&headers, "Maintainer-Email")
                            .iter()
                    )
                        .map(|s| NameEmail::from(s.as_str()))
                        .collect::<Vec<_>>(),
                    license: get_one(&headers, "License-Expression")?.to_string(),
                    urls,
                    files,
                });
            }
        }
        Ok(packages)
    }
}

fn parse_colon_fields(output: &str) -> HashMap<String, Vec<String>> {
    let mut map = HashMap::new();
    for line in output.lines() {
        if let Some((field, value)) = line.split_once(':') {
            let value = value.trim().to_string();
            map.entry(field.trim().to_string()).and_modify(|vec: &mut Vec<String>| vec.push(value.clone())).or_insert(vec![value]);
        }
    }
    map
}

fn parse_rfc_822_headers(bytes: &[u8]) -> Result<HashMap<String, Vec<String>>> {
    let mut ret = HashMap::new();
    let email = mailparse::parse_mail(&bytes)?;
    for header in email.get_headers() {
        ret.entry(header.get_key())
            .or_insert_with(Vec::new)
            .push(header.get_value());
    }
    Ok(ret)
}

fn parse_rfc_822_email(bytes: &[u8]) -> Result<HashMap<String, Vec<String>>> {
    let mut ret = HashMap::new();
    let email = mailparse::parse_mail(&bytes)?;
    for header in email.get_headers() {
        ret.entry(header.get_key())
            .or_insert_with(Vec::new)
            .push(header.get_value());
    }
    Ok(ret)
}

#[cfg(test)]
mod tests {
    use crate::file_info::*;
    use color_eyre::eyre::*;
    #[test]
    fn test_main() -> Result<()> {
        println!("{:?}", DebPackageInfo::try_from("fake")?);
        println!("{:?}", RpmPackageInfo::try_from("fake")?);
        println!("{:?}", PythonSitePackages::try_from("/fake")?);
        Ok(())
    }
}

fn get_one<'a>(
    map: &'a HashMap<String, Vec<String>>,
    key: &'a str,
) -> Result<&'a str> {
    map
        .get(key)
        .ok_or(eyre!("{:?} not found", key))
        .and_then(|vec| if vec.len() == 1 { Ok(vec[0].as_str()) } else { Err(eyre!("more than one value for key {:?}", key)) })
}


fn get_many<'a>(
    map: &'a HashMap<String, Vec<String>>,
    key: &'a str,
) -> Vec<String> {
    map
        .get(key)
        .map(|vec| vec.clone())
        .unwrap_or_else(|| vec![])
}
