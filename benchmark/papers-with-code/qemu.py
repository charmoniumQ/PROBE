import tarfile
import tempfile
import sys
import typing
import contextlib
import enum
import urllib.parse
import secrets
import pathlib
import datetime
import bitmath
import subprocess
import httpx


class Disk(pathlib.Path):
    pass


class Architecture(enum.StrEnum):
    X86_64 = enum.auto()


_resources_dir = pathlib.Path(".qemu")
if not _resources_dir.exists():
    _resources_dir.mkdir()


def _bitmath_to_qemu(value: bitmath.Bitmath) -> str:
    return f"{value / bitmath.MiB(1)}M"


def bake_debian_disk(
        size: bitmath.Bitmath,
        architecture: Architecture,
        version: str = "bookworm",
) -> Disk:
    debian_disk = Disk(_resources_dir / f"debian_{version}.raw")
    if not debian_disk.exists():
        deb_arch = {
            Architecture.X86_64: "amd64",
        }[architecture]
        netboot_url = f"https://deb.debian.org/debian/dists/{version}/main/installer-{deb_arch}/current/images/netboot/netboot.tar.gz"
        # https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/mini.iso
        netboot_path = _resources_dir / urllib.parse.quote_plus(netboot_url)
        netboot_path.write_bytes(httpx.get(netboot_url).content)
        subprocess.run(
            ["qemu-img", "create", "-f", "raw", str(debian_disk), "10G"],
            # This disk size doesn't matter because it is just the base disk, not the returned user disk.
            # It gets stored sparesely, so no harm in overestimating.
            check=True,
        )
        with tempfile.TemporaryDirectory() as _tmp_dir:
            tmp_dir = pathlib.Path(_tmp_dir)
            with tarfile.open(netboot_path, "r:gz") as tarfile_obj:
                tarfile_obj.extractall(tmp_dir)
                qemu_run(
                    debian_disk,
                    ["true"],
                    "-kernel",
                    str(tmp_dir / "vmlinuz"),
                    "-initrd",
                    str(tmp_dir / "initrd.gz"),
                    "-append",
                    "root=/dev/sda console=ttyS0",
                    timeout=datetime.timedelta(minutes=5),
                    capture_output=False,
                    check=True,
                )
    disk = Disk(_resources_dir / ("disk_" + secrets.token_hex(16)))
    # Raw is fastest, but non-base layers have to be qcow2
    install_proc = subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", "-b", str(debian_disk), str(disk), _bitmath_to_qemu(size)],
        check=False,
        text=True,
        capture_output=True,
    )
    if install_proc.returncode != 0:
        print(install_proc.stdout, file=sys.stdout)
        print(install_proc.stderr, file=sys.stderr)
        raise RuntimeError("qemu-img failed")
    return disk


@contextlib.contextmanager
def make_temporary_disk(disk: Disk) -> typing.Iterator[None]:
    try:
        yield
    finally:
        disk.unlink()


def qemu_run(
        disk: Disk,
        cmd: list[str],
        qemu_system: str = "x86_64",
        cpu_model: str = "host",
        n_cpus: int = 1,
        memory: bitmath.Bitmath = bitmath.GiB(1),
        timeout: datetime.timedelta | None = None,
        input: str | None = None,
        capture_output: bool = False,
        check: bool = False,
        *cmd_args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            f"qemu-system-{qemu_system}",
            "-smp",
            f"cpus={n_cpus}",
            "-m",
            _bitmath_to_qemu(memory),
            "-drive",
            f"file={disk!s}",
            "-nographic",
            "-serial",
            "mon:stdio",
            "-boot",
            "order=c",
            *cmd_args,
        ],
        timeout=int(timeout.total_seconds()) if timeout else None,
        input=input,
        capture_output=capture_output,
        text=True,
        check=check,
    )


###################################################################################################

def get_qemu_image(
        base: str,
        version: str,
        architecture: Architecture,
) -> Image:
    image = Image(_images_dir / urllib.parse.quote_plus(base + ":" + version))
    if image.exists():
        return image
    else:
        image_url = _image_urls[base, version, architecture]
        image.write_bytes(httpx.get(image_url).content)
        return image


def make_qemu_hd(
        size: bitmath.Bitmath,
        base: Image | Disk,
        type: str = "qcow2",
) -> Disk:
    disk = Disk(_disks_dir / secrets.token_hex(16))
    create_disk_proc = subprocess.run(
        [
            "qemu-img",
            "create",
            "-f",
            type,
            *(["-b", str(base)] if isinstance(base, Disk) else []),
            str(disk),
            f"{size / bitmath.MiB(1):.0f}M",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if create_disk_proc.returncode == 0:
        if isinstance(base, Image):
            qemu_run(
                disk,
                [],
                cdrom=base,
                timeout=datetime.timedelta(minutes=10),
            )
        return disk
    else:
        disk.unlink()
        raise RuntimeError(create_disk_proc.stdout + "\n\n" + create_disk_proc.stderr)
