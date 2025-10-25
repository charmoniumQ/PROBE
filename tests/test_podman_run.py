import asyncio
import pathlib
import shlex
import shutil
import subprocess
import sys
import pytest


# This is necessary because unshare(...) seems to be blocked in the latest github runners on Ubuntu 24.04.
# Also fixtures can't be used in a pytest.mark.skipif
def does_podman_work() -> bool:
    return shutil.which("podman") is not None and subprocess.run(
        ["podman", "run", "--rm", "ubuntu:24.04", "pwd"],
        check=False,
    ).returncode == 0


def does_nix_work() -> bool:
    return shutil.which("nix") is not None and subprocess.run(
        ["nix", "flake", "show"],
        check=False,
    ).returncode == 0


@pytest.fixture(scope="session")
def nix_built_probe() -> pathlib.Path:
    cmd = ["nix", "build", "--no-link", "--print-out-paths", ".#probe"]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ValueError(f"stderr: {proc.stderr}\n\nstdout: {proc.stdout}")
    return pathlib.Path(proc.stdout.strip())


@pytest.mark.skipif(not does_podman_work() or not does_nix_work(), reason="Podman or Nix doesn't work")
@pytest.mark.parametrize(
    "image",
    [
        "ubuntu:12.04",
        "debian:8",
        "centos:7",
        # Alpine uses musl c, which should be interesting
    ],
)
@pytest.mark.asyncio
async def test_podman_run(
        image: str,
        nix_built_probe: pathlib.Path,
) -> None:
    _nix_built_probe = nix_built_probe
    nix_store = _nix_built_probe.parent
    probe = str(_nix_built_probe / "bin/probe")
    cmd = [
        "podman",
        "run",
        "--rm",
        f"--volume={nix_store!s}:{nix_store!s}:ro",
        image,
        "sh",
        "-c",
        f"{probe} record ls ; {probe} record --overwrite env ; {probe} py export dataflow-graph",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return_code = await proc.wait()
    if return_code != 0:
        sys.stdout.buffer.write(stdout)
        sys.stdout.buffer.write(stderr)
        raise RuntimeError(f"Process '{shlex.join(cmd)} exited with {return_code}")
