import os
import random
import shutil
import pathlib
import shlex
import subprocess
import pytest


project_root = pathlib.Path(__file__).resolve().parent.parent


def bash(*cmd: str) -> list[str]:
    return ["bash", "-c", shlex.join(cmd).replace(" redirect_to ", " > ")]


def bash_multi(*cmds: list[str]) -> list[str]:
    return ["bash", "-c", " && ".join(
        shlex.join(cmd).replace(" and ", " && ").replace(" redirect_to ", " > ")
        for cmd in cmds
    )]


c_hello_world = r"""
#include <stdio.h>
#include <fcntl.h>
int main() {
    open(".", 0);
    printf("hello world\n");
    return 0;
}
"""


java_subprocess_hello_world = """
public class HelloWorld {
    public static void main(String[] args) throws java.io.IOException, InterruptedException {
        System.exit(
            new ProcessBuilder("echo", "Hello", "world")
            .redirectOutput(ProcessBuilder.Redirect.INHERIT)
            .start()
            .waitFor()
        );
   }
}
"""


true_path = shutil.which("true")
assert true_path
false_path = shutil.which("false")


commands = {
    "echo": ["echo", "hi"],
    "head": ["head", "test_file.txt"],
    "c-hello": bash_multi(
        ["echo", c_hello_world, "redirect_to", "test.c"],
        ["gcc", "test.c"],
        ["./a.out"],
    ),
    "java-subprocess-hello": bash_multi(
        ["echo", java_subprocess_hello_world, "redirect_to", "HelloWorld.java"],
        ["javac", "HelloWorld.java"],
        ["java", "HelloWorld"],
    ),
    "python-hello": bash_multi(
        ["python", "-c", "print(4)"],
        [true_path],
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
}


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


@pytest.fixture(scope="session")
def scratch_directory_parent() -> pathlib.Path:
    real_scratch_directory_parent = pathlib.Path(__file__).resolve().parent / "tmp"
    if real_scratch_directory_parent.exists():
        shutil.rmtree(real_scratch_directory_parent)
    real_scratch_directory_parent.mkdir()
    return real_scratch_directory_parent


@pytest.fixture(scope="function")
def scratch_directory(
        request: pytest.FixtureRequest,
        scratch_directory_parent: pathlib.Path,
) -> pathlib.Path:
    """An predictable, persistent, empty directory.

    This directory will be ignored by Git, but persistent after the test's
    completion for manual inspection. It gets cleared every re-test however.

    """
    scratch_dir = scratch_directory_parent / request.node.nodeid.replace("/", "_")
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)
    scratch_dir.mkdir()
    return scratch_dir


@pytest.mark.parametrize("command", commands.values(), ids=commands.keys())
def test_unmodified_cmds(
        scratch_directory: pathlib.Path,
        command: list[str],
) -> None:
    (scratch_directory / "test_file.txt").write_text("hello world")
    print(scratch_directory)
    print(shlex.join(command))
    subprocess.run(command, check=True, cwd=scratch_directory)


@pytest.mark.parametrize("copy_files", [
    "none",
    "lazily",
    "eagerly",
])
@pytest.mark.parametrize("debug", [False, True], ids=["opt", "dbg"])
@pytest.mark.parametrize("command", commands.values(), ids=commands.keys())
def test_cmds(
        scratch_directory: pathlib.Path,
        copy_files: str,
        debug: bool,
        command: list[str],
        does_podman_work: bool,
        does_docker_work: bool,
        does_buildah_work: bool,
) -> None:
    (scratch_directory / "test_file.txt").write_text("hello world")
    print(scratch_directory)

    cmd = ["probe", "record", *(["--debug"] if debug else []), "--copy-files", copy_files, *command]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=scratch_directory)

    should_have_copy_files = copy_files in {"eagerly", "lazily"}
    cmd = ["probe", "validate", *(["--should-have-files"] if should_have_copy_files else [])]
    print(shlex.join(cmd))

    cmd = ["probe", "export", "debug-text"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=scratch_directory)

    cmd = ["probe", "export", "ops-graph", "test.png"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=scratch_directory)

    cmd = ["probe", "export", "dataflow-graph", "test.png"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=scratch_directory)

    if should_have_copy_files:

        if does_buildah_work and does_podman_work:
            cmd = ["probe", "export", "oci-image", "probe-command-test:latest"]
            print(shlex.join(cmd))
            subprocess.run(cmd, check=True, cwd=scratch_directory)
            assert shutil.which("podman"), "podman required for this test; should be in the nix flake?"
            cmd = ["podman", "run", "--rm", "probe-command-test:latest"]
            print(shlex.join(cmd))
            subprocess.run(cmd, check=True, cwd=scratch_directory)

        if does_buildah_work and does_docker_work:
            cmd = ["probe", "export", "docker-image", "probe-command-test:latest"]
            print(shlex.join(cmd))
            subprocess.run(cmd, check=True, cwd=scratch_directory)
            assert shutil.which("docker"), "podman required for this test; should be in the nix flake?"
            cmd = ["docker", "run", "--rm", "probe-command-test:latest"]
            print(shlex.join(cmd))
            subprocess.run(cmd, check=True, cwd=scratch_directory)


def test_big_env(
        scratch_directory: pathlib.Path,
) -> None:
    subprocess.run(
        ["probe", "record", "--debug", "--copy-files", "none", *commands["c-hello"]],
        env={
            **os.environ,
            "A": "B"*10000,
        },
        check=True,
        cwd=scratch_directory,
    )


def test_fail(
        scratch_directory: pathlib.Path,
) -> None:
    assert false_path
    cmd = ["probe", "record", "--copy-files", "none", false_path]
    proc = subprocess.run(cmd, check=False, cwd=scratch_directory)
    assert proc.returncode != 0
