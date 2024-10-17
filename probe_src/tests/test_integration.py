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
    ["head", "../../../flake.nix"],
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
    ["probe", "record", "--copy-files"],
]


@pytest.mark.parametrize("mode", modes)
@pytest.mark.parametrize("command", commands)
def test_cmds(mode: list[str], command: list[str]) -> None:
    tmpdir.mkdir(exist_ok=True)
    (tmpdir / "probe_log").unlink(missing_ok=True)

    cmd = [*mode, *command]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=tmpdir)

    cmd = ["probe", "validate", *(["--should-have-files"] if "copy-files" in mode else [])]
    print(shlex.join(cmd))

    if any("gcc" in arg for arg in command):
        # GCC creates many threads and processes, so this stuff is pretty slow.
        return

    cmd = ["probe", "export", "ops-graph", "test.png"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=tmpdir)

    cmd = ["probe", "export", "dataflow-graph", "test.png"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=tmpdir)

    if "--copy-files" in mode:

        cmd = ["probe", "export", "oci-image", "probe-command-test:latest"]
        print(shlex.join(cmd))
        subprocess.run(cmd, check=True, cwd=tmpdir)
        assert shutil.which("podman"), "podman required for this test; should be in the nix flake?"
        cmd = ["podman", "run", "--rm", "probe-command-test:latest"]
        print(shlex.join(cmd))
        subprocess.run(cmd, check=True, cwd=tmpdir)

        cmd = ["probe", "export", "docker-image", "probe-command-test:latest"]
        print(shlex.join(cmd))
        subprocess.run(cmd, check=True, cwd=tmpdir)
        assert shutil.which("docker"), "podman required for this test; should be in the nix flake?"
        cmd = ["docker", "run", "--rm", "probe-command-test:latest"]
        print(shlex.join(cmd))
        subprocess.run(cmd, check=True, cwd=tmpdir)
