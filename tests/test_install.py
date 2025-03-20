import tempfile
import pathlib
import subprocess
import shutil


dockerfile = """
FROM ubuntu:24.04
RUN apt-get update
RUN apt-get install --yes curl
ENV USER=root

# Test container install directions from README
RUN curl -fsSL https://install.determinate.systems/nix | sh -s -- install linux --extra-conf "sandbox = false" --init none --no-confirm
ENV PATH="${PATH}:/nix/var/nix/profiles/default/bin"
RUN nix profile install --accept-flake-config nixpkgs#cachix
RUN cachix use charmonium
"""


def test_podman_install() -> None:
    podman = shutil.which("podman")
    assert podman
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        (tmpdir / "Dockerfile").write_text(dockerfile)
        subprocess.run(
            [
                podman,
                "build",
                ".",
                "--tag=test:0.1.0",
            ],
            cwd=tmpdir,
            check=True,
        )
    subprocess.run(
        [
            podman,
            "run",
            "--volume",
            str(pathlib.Path().resolve()) + ":/PROBE",
            "test:0.1.0",
            "sh",
            "-c",
            " && ".join([
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
