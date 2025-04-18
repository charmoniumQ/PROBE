import os
import random
import shutil
import pytest
import pathlib
import shlex
import subprocess


project_root = pathlib.Path(__file__).resolve().parent.parent.parent
tmpdir = pathlib.Path(__file__).resolve().parent / "tmp"


def bash(*cmds: str) -> list[str]:
    return ["bash", "-c", shlex.join(cmds).replace(" and ", " && ").replace(" redirect_to ", " > ")]


commands = [
    ["echo", "hi"],
    ["head", "../../flake.nix"],
    bash(
        "echo",
        "#include <stdio.h>\n#include <fcntl.h>\nint main() {open(\".\", 0); printf(\"hello world\\n\"); return 0; }",
        "redirect_to",
        "test.c",
        "and",
        "gcc",
        "test.c",
        "and",
        "./a.out",
    ),
    # bash(
    #     *bash(
    #         *bash("echo", "hi", "redirect_to", "file0"),
    #         "and",
    #         *bash("cat", "file0", "file0", "redirect_to", "file1"),
    #     ),
    #     "and",
    #     *bash(
    #         *bash("cat", "file0", "file1", "redirect_to", "file2"),
    #         "and",
    #         *bash("cat", "file0", "file2", "redirect_to", "file3"),
    #     ),
    # ),
]

modes = [
    ["probe", "record"],
    ["probe", "record", "--debug"],
    ["probe", "record", "--copy-files", "none"],
    ["probe", "record", "--copy-files", "lazily"],
    ["probe", "record", "--copy-files", "eagerly"],
]


# This is necessary because unshare(...) seems to be blocked in the latest github runners on Ubuntu 24.04.
@pytest.fixture(scope="session")
def does_podman_work() -> bool:
    return subprocess.run(["podman", "run", "--rm", "ubuntu:24.04", "pwd"], capture_output=True, check=False).returncode == 0


@pytest.fixture(scope="session")
def does_docker_work() -> bool:
    return subprocess.run(["docker", "run", "--rm", "ubuntu:24.04", "pwd"], capture_output=True, check=False).returncode == 0


@pytest.fixture(scope="session")
def does_buildah_work() -> bool:
    name = f"probe-{random.randint(0, 2**32 - 1):08x}"
    proc = subprocess.run(["buildah", "from", "--name", name, "scratch"], capture_output=True, text=True)
    return proc.returncode == 0 and subprocess.run(["buildah", "remove", name], capture_output=True, check=False).returncode == 0


@pytest.mark.parametrize("mode", modes)
@pytest.mark.parametrize("command", commands)
def test_cmds(
        mode: list[str],
        command: list[str],
        does_podman_work: bool,
        does_docker_work: bool,
        does_buildah_work: bool,
) -> None:
    tmpdir.mkdir(exist_ok=True)
    (tmpdir / "probe_log").unlink(missing_ok=True)

    cmd = [*mode, *command]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=tmpdir)

    copy_files = "eagerly" in mode or "lazily" in mode
    cmd = ["probe", "validate", *(["--should-have-files"] if copy_files else [])]
    print(shlex.join(cmd))

    if any("gcc" in arg for arg in command):
        # GCC creates many threads and processes, so this stuff is pretty slow.
        return

    cmd = ["probe", "export", "debug-text"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=tmpdir)

    cmd = ["probe", "export", "ops-graph", "test.png"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=tmpdir)

    cmd = ["probe", "export", "dataflow-graph", "test.png"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=tmpdir)

    if copy_files:

        if does_buildah_work and does_podman_work:
            cmd = ["probe", "export", "oci-image", "probe-command-test:latest"]
            print(shlex.join(cmd))
            subprocess.run(cmd, check=True, cwd=tmpdir)
            assert shutil.which("podman"), "podman required for this test; should be in the nix flake?"
            cmd = ["podman", "run", "--rm", "probe-command-test:latest"]
            print(shlex.join(cmd))
            subprocess.run(cmd, check=True, cwd=tmpdir)

        if does_buildah_work and does_docker_work:
            cmd = ["probe", "export", "docker-image", "probe-command-test:latest"]
            print(shlex.join(cmd))
            subprocess.run(cmd, check=True, cwd=tmpdir)
            assert shutil.which("docker"), "podman required for this test; should be in the nix flake?"
            cmd = ["docker", "run", "--rm", "probe-command-test:latest"]
            print(shlex.join(cmd))
            subprocess.run(cmd, check=True, cwd=tmpdir)


def test_big_env() -> None:
    tmpdir.mkdir(exist_ok=True)
    (tmpdir / "probe_log").unlink(missing_ok=True)
    subprocess.run(
        [*modes[0], *commands[2]],
        env={
            **os.environ,
            "A": "B"*10000,
        },
        check=True,
        cwd=tmpdir,
    )


def test_fail() -> None:
    tmpdir.mkdir(exist_ok=True)
    (tmpdir / "probe_log").unlink(missing_ok=True)
    cmd = ["probe", "record", "false"]
    proc = subprocess.run(cmd, check=False, cwd=tmpdir)
    assert proc.returncode != 0
