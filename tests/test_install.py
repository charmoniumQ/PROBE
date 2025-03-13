import pathlib
import pytest
import subprocess
import shutil


podman = shutil.which("podman")


def test_podman_install() -> None:
    subprocess.run(
        [
            "podman",
            "run",
            "--volume",
            str(pathlib.Path().resolve()) + ":/storage",
            "debian:latest"
            "sh",
            "-c",
            " && ".join([
                "apt-get update",
                "apt-get install curl",
                'curl -fsSL https://install.determinate.systems/nix | sh -s -- install linux --extra-conf "sandbox = false" --init none --no-confirm',
                'export PATH="${PATH}:/nix/var/nix/profiles/default/bin"',
                "nix profile install --accept-flake-config nixpkgs#cachix",
                "cachix use charmonium",
                "nix run github:charmoniumQ/PROBE -- record ls",
                "nix profile install github:charmoniumQ/PROBE",
                "probe export debug-text",
            ]),
        ]
    )
