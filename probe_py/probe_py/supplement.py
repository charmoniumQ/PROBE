from __future__ import annotations
from collections.abc import Iterable as Itb, Mapping as Map
import itertools
import json
import pathlib
import re
import shutil
import subprocess
import dulwich.repo
import dulwich.porcelain
import msgspec
from . import util


class Supplemental(msgspec.Struct, frozen=True):
    files: dict[pathlib.Path, FileInfo]

    @staticmethod
    def from_files(paths: Itb[pathlib.Path]) -> Supplemental:
        files = {path: FileInfo.create(path) for path in paths}
        return Supplemental(files)


pip_cache: dict[tuple[pathlib.Path, str], PipPackage | None] = {}


class PipPackage(msgspec.Struct, frozen=True):
    name: str
    version: str
    authors: Itb[tuple[str, str]]
    maintainers: Itb[tuple[str, str]]
    urls: Map[str, str]
    licenses: Itb[str]

    @staticmethod
    def from_name(python: pathlib.Path, name: str) -> PipPackage | None:
        if (python, name) not in pip_cache:
            proc = subprocess.run(
                [
                    python,
                    "-c",
                    "import importlib.metadata as m, json; d = m.distribution(name); print(json.dumps({'version': d.version, 'authors': d.metadata.get('Author'), 'author_emails': d.metadata.get_all('Author-Email'), 'maintainers': d.metadata.get('Maintainer'), 'maintainer_emails': d.metadata.get_all('Maintainer-Email'), 'urls': d.metadata.get_all('Project-URL'), 'licenses': d.metadata.get_all('License-Expression')}))".replace(
                        "name", repr(name)
                    ),
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                metadata = json.loads(proc.stdout)
                pip_cache[(python, name)] = PipPackage(
                    name,
                    metadata["version"],
                    list(
                        itertools.zip_longest(
                            metadata["authors"] or [], metadata["author_emails"] or []
                        )
                    ),
                    list(
                        itertools.zip_longest(
                            metadata["maintainers"] or [],
                            metadata["maintainer_emails"] or [],
                        )
                    ),
                    {
                        url.split(", ")[0]: url.split(", ")[1]
                        for url in metadata["urls"] or []
                    },
                    metadata["licenses"] or [],
                )
            else:
                print(proc.stderr)
                pip_cache[(python, name)] = None
        return pip_cache[(python, name)]


class FileInfo(msgspec.Struct, frozen=True):
    stat_result: StatResult
    magic_info: MagicInfo | None
    venv_file_info: VenvFileInfo | None
    git_file_info: GitFileInfo | None
    dpkg_info: DpkgInfo | None
    rpm_info: RpmInfo | None

    @staticmethod
    def create(path: pathlib.Path) -> FileInfo:
        return FileInfo(
            # StatResult.create(path),
            # MagicInfo.create(path),
            # VenvFileInfo.create(path),
            # GitFileInfo.create(path),
            # DpkgInfo.create(path),
            # RpmInfo.create(path),
            StatResult.create(path),
            None,
            VenvFileInfo.create(path),
            None,
            None,
            None,
        )


class StatResult(msgspec.Struct, frozen=True):
    st_mode: int
    st_ino: int
    st_dev: int
    st_nlink: int
    st_uid: int
    st_gid: int
    st_size: int
    st_atime: float
    st_mtime: float
    st_ctime: float
    st_atime_ns: int
    st_mtime_ns: int
    st_ctime_ns: int

    @staticmethod
    def create(path: pathlib.Path) -> StatResult:
        stat = path.stat()
        return StatResult(
            st_mode=stat.st_mode,
            st_ino=stat.st_ino,
            st_dev=stat.st_dev,
            st_nlink=stat.st_nlink,
            st_uid=stat.st_uid,
            st_gid=stat.st_gid,
            st_size=stat.st_size,
            st_atime=stat.st_atime,
            st_mtime=stat.st_mtime,
            st_ctime=stat.st_ctime,
            st_atime_ns=stat.st_atime_ns,
            st_mtime_ns=stat.st_mtime_ns,
            st_ctime_ns=stat.st_ctime_ns,
        )


class MagicInfo(msgspec.Struct, frozen=True):
    type_string: str
    mime_type: str
    mime_encoding: str

    @staticmethod
    def create(path: pathlib.Path) -> MagicInfo | None:
        procs = [
            subprocess.run(
                ["file", "--brief", str(path)], capture_output=True, text=True
            ),
            subprocess.run(
                ["file", "--brief", "--mime-encoding", str(path)],
                capture_output=True,
                text=True,
            ),
            subprocess.run(
                ["file", "--brief", "--mime-encoding", str(path)],
                capture_output=True,
                text=True,
            ),
        ]
        if any(proc.returncode != 0 for proc in procs):
            return None
        else:
            return MagicInfo(
                procs[0].stdout.strip(),
                procs[1].stdout.strip(),
                procs[2].stdout.strip(),
            )


venv_cache: dict[pathlib.Path, Map[str, list[str]]] = {}


class VenvFileInfo(msgspec.Struct, frozen=True):
    venv_path: pathlib.Path
    packages: Itb[PipPackage]

    @staticmethod
    def create(path: pathlib.Path) -> VenvFileInfo | None:
        for ancestor in util.ancestors(path):
            venv_root = ancestor
            if (venv_root / "bin/python").exists() and (venv_root / "bin/pip").exists():
                python = venv_root / "bin/python"
                site_packages_candidates = [
                    ancestor
                    for ancestor in util.ancestors(path)
                    if ancestor.name == "site-packages"
                ]
                if site_packages_candidates:
                    site_packages = site_packages_candidates[0]
                    if path.is_relative_to(site_packages):
                        if venv_root not in venv_cache:
                            proc = subprocess.run(
                                [
                                    python,
                                    "-c",
                                    "import importlib.metadata as m, json; print(json.dumps(m.packages_distributions()))",
                                ],
                                capture_output=True,
                                text=True,
                            )
                            venv_cache[venv_root] = (
                                json.loads(proc.stdout) if proc.returncode == 0 else {}
                            )
                            if proc.returncode != 0:
                                raise RuntimeError()
                        packages_distributions = venv_cache[venv_root]
                        for ancestor in util.ancestors(path.relative_to(site_packages)):
                            possible_import_name = ".".join(ancestor.parts)
                            if package_names := packages_distributions.get(
                                possible_import_name
                            ):
                                packages2 = [
                                    PipPackage.from_name(python, package_name)
                                    for package_name in package_names
                                ]
                                packages = [
                                    package
                                    for package in packages2
                                    if package is not None
                                ]
                                break
                        else:
                            packages = []
                    else:
                        packages = []
                else:
                    packages = []
                return VenvFileInfo(
                    venv_root,
                    packages,
                )
        else:
            return None


class GitFileInfo(msgspec.Struct, frozen=True):
    repo: pathlib.Path

    @staticmethod
    def create(path: pathlib.Path) -> GitFileInfo | None:
        try:
            repo = dulwich.repo.Repo.discover(path.parent)
        except dulwich.errors.NotGitRepository:
            return None
        else:
            return GitFileInfo(pathlib.Path(repo.path))


dpkg = shutil.which("dpkg")


class DpkgInfo(msgspec.Struct, frozen=True):
    name: str
    version: str
    homepage: str
    original_maintainer: str
    maintainer: str

    # TODO: https://github.com/daald/dpkg-licenses

    @staticmethod
    def create(path: pathlib.Path) -> DpkgInfo | None:
        if not dpkg:
            return None
        proc = subprocess.run(
            [dpkg, "--search", str(path)], capture_output=True, text=True
        )
        if proc.returncode != 0:
            return None
        else:
            package = proc.stdout.strip().split(":")[0].split(", ")[0]
            proc = subprocess.run(
                [dpkg, "--status", package], capture_output=True, text=True
            )
            if proc.returncode != 0:
                return None
            else:
                output = proc.stdout.strip()
                name = re.search("Package: (.*)", output)
                version = re.search("Version: (.*)", output)
                homepage = re.search("Homepage: (.*)", output)
                maintainer = re.search("Maintainer: (.*)", output)
                original_maintainer = re.search("Original-Maintainer: (.*)", output)
                assert (
                    name and version and homepage and maintainer and original_maintainer
                )
                return DpkgInfo(
                    name.group(1),
                    version.group(1),
                    homepage.group(1),
                    original_maintainer.group(1),
                    maintainer.group(1),
                )


rpm = shutil.which("rpm")


class RpmInfo(msgspec.Struct, frozen=True):
    name: str
    version: str
    release: str
    license: str
    homepage: str
    build_host: str
    packager: str

    @staticmethod
    def create(path: pathlib.Path) -> RpmInfo | None:
        if not rpm:
            return None
        proc = subprocess.run(
            [rpm, "--query", "--file", str(path)], capture_output=True, text=True
        )
        if proc.returncode != 0:
            return None
        else:
            package = proc.stdout.strip()
            proc = subprocess.run(
                [rpm, "--query", "--info", package], capture_output=True, text=True
            )
            if proc.returncode != 0:
                return None
            else:
                output = proc.stdout
                name = re.search("Name *: (.*)", output)
                version = re.search("Version *: (.*)", output)
                release = re.search("Release *: (.*)", output)
                license = re.search("License *: (.*)", output)
                homepage = re.search("URL *: (.*)", output)
                build_host = re.search("Build Host *: (.*)", output)
                packager = re.search("Packager *: (.*)", output)
                assert (
                    name
                    and version
                    and release
                    and license
                    and homepage
                    and build_host
                    and packager
                )
                return RpmInfo(
                    name.group(1),
                    version.group(1),
                    release.group(1),
                    license.group(1),
                    homepage.group(1),
                    build_host.group(1),
                    packager.group(1),
                )
