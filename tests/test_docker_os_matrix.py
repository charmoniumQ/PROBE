import asyncio
import pathlib
import shlex
import subprocess
import sys
import typing
import pytest


@pytest.fixture(scope="session")
def nix_built_probe() -> pathlib.Path:
    cmd = ["nix", "build", "--no-link", "--print-out-paths", ".#probe"]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )
    return pathlib.Path(proc.stdout.strip())



#@pytest.mark.skip(reason="Very slow")
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
    cmd = [
        "podman",
        "run",
        "--rm",
        f"--volume={nix_store!s}:{nix_store!s}:ro",
        image,
        str(_nix_built_probe / "bin/probe"),
        "record",
        "env",
        "ls",
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
