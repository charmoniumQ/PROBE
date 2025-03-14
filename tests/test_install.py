import pathlib
import subprocess
import shutil


def test_podman_install() -> None:
    podman = shutil.which("podman")
    assert podman
    subprocess.run(
        [
            podman,
            "run",
            "--volume",
            str(pathlib.Path().resolve()) + ":/PROBE",
            "debian:latest",
            "sh",
            "-c",
            " && ".join([
                "apt-get update",
                "apt-get install --yes curl",
                "export USER=root",

                # Test container install directions from README
                'curl -fsSL https://install.determinate.systems/nix | sh -s -- install linux --extra-conf "sandbox = false" --init none --no-confirm',
                'export PATH="${PATH}:/nix/var/nix/profiles/default/bin"',
                "nix profile install --accept-flake-config nixpkgs#cachix",
                "cachix use charmonium",

                # Test temporary run directions
                "nix run /PROBE -- --help",

                # Test permanent installation directions
                "nix profile install /PROBE",

                # Test recording in container
                "probe record ls",

                # Test Rust -> Python handoff
                "probe export debug-text",
            ]),
        ],
        check=True,
    )
