import random
import shutil
import pathlib
import shlex
import subprocess
import pytest


project_root = pathlib.Path(__file__).resolve().parent.parent


PROBE = str(project_root / "cli-wrapper/target/release/probe")


def bash(*cmd: str) -> list[str]:
    return ["bash", "-c", shlex.join(cmd).replace(" redirect_to ", " > ")]


def bash_multi(*cmds: list[str]) -> list[str]:
    return ["bash", "-c", " && ".join(
        shlex.join(cmd).replace(" pipe ", " | ").replace(" redirect_to ", " > ")
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

example_path = project_root / "tests/examples"


simple_commands = {
    "echo": [str(example_path / "echo.exe"), "hello", "world"],
    "cat": [str(example_path / "cat.exe"), "test_file.txt"],
    "fcat": [str(example_path / "fcat.exe"), "test_file.txt"],
    "createFile": [f"{project_root}/tests/examples/createFile.exe"],
    "mmap_cat": [str(example_path / "mmap_cat.exe"), "test_file.txt"],
    # skip million_stats because it takes a very long time.
    # Re-enable once we hvae a faster analysis.
    # "million_stats": [str(example_path / "multiple_stats.exe"), str(int(1e6)), "test_file.txt"],
    # See https://github.com/charmoniumQ/PROBE/pull/135
    "ls": [str(example_path / "ls.exe"), "."],
    "coreutils_echo": ["echo", "hi"],
    "coreutils_cat": ["cat", "test_file.txt"],
    "python_hello": ["python", "-c", "print(4)"],
}

complex_commands = {
    "hello_world_pthreads": [str(example_path / "hello_world_pthreads.exe")],
    "mutex": [str(example_path / "mutex.exe")],
    "fork_exec": [str(example_path / "fork_exec.exe"), str(example_path / "echo.exe"), "hello", "world"],
    "diff": ["diff", "test_file.txt", "test_file.txt"],
    "bash_multi": bash_multi(
        # echo is a bash bulitin
        # so we use echo_path to get the real echo executable
        [str(example_path / "echo.exe"), "hi"],
        [str(example_path / "echo.exe"), "hello"],
        [str(example_path / "echo.exe"), "world"],
    ),
    "echo_cat": bash_multi(
        [str(example_path / "echo.exe"), "hi", "redirect_to", "test_file"],
        [str(example_path / "cat.exe"), "test_file", "redirect_to", "test_file2"],
    ),
    "pipe": bash_multi(
        # echo is a bash bulitin
        # so we use echo_path to get the real echo executable
        [str(example_path / "echo.exe"), "hi", "pipe", str(example_path / "cat.exe"), "redirect_to", "test_file"],
    ),
    "c_hello": bash_multi(
        ["echo", c_hello_world, "redirect_to", "test.c"],
        ["gcc", "test.c"],
        ["./a.out"],
    ),
    "java_subprocess_hello": bash_multi(
        ["echo", java_subprocess_hello_world, "redirect_to", "HelloWorld.java"],
        ["javac", "HelloWorld.java"],
        ["java", "HelloWorld"],
    ),
    "bash_in_bash": bash_multi(
        bash_multi(
            ["echo", "hi", "redirect_to", "file0"],
            ["cat", "file0", "file0", "redirect_to", "file1"],
        ),
        bash_multi(
            ["cat", "file0", "file1", "redirect_to", "file2"],
            ["cat", "file0", "file2", "redirect_to", "file3"],
        ),
    ),
}


# This is necessary because unshare(...) seems to be blocked in the latest github runners on Ubuntu 24.04.
@pytest.fixture(scope="session")
def does_podman_work() -> bool:
    return subprocess.run(["podman", "run", "--rm", "ubuntu:24.04", "pwd"], check=False).returncode == 0


@pytest.fixture(scope="session")
def does_docker_work() -> bool:
    return subprocess.run(["docker", "run", "--rm", "ubuntu:24.04", "pwd"], check=False).returncode == 0


@pytest.fixture(scope="session")
def does_buildah_work() -> bool:
    name = f"probe-{random.randint(0, 2**32 - 1):08x}"
    proc = subprocess.run(["buildah", "from", "--name", name, "scratch"])
    return proc.returncode == 0 and subprocess.run(["buildah", "rm", name], check=False).returncode == 0


@pytest.fixture(scope="session")
def compile_examples() -> None:
    subprocess.run(
        ["make", "--directory", str(project_root / "tests/examples")],
        check=True,
    )


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
    suffix: str = request.node.nodeid.replace("/", "_")
    scratch_dir = scratch_directory_parent / suffix
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)
    scratch_dir.mkdir()
    return scratch_dir


@pytest.mark.parametrize("copy_files", [
    "none",
    "lazily",
    "eagerly",
])
@pytest.mark.parametrize("debug", [False, True], ids=["opt", "dbg"])
@pytest.mark.parametrize(
    "command",
    {**simple_commands, **complex_commands}.values(),
    ids={**simple_commands, **complex_commands}.keys(),
)
@pytest.mark.timeout(20)
def test_record(
        scratch_directory: pathlib.Path,
        copy_files: str,
        debug: bool,
        command: list[str],
        does_podman_work: bool,
        does_docker_work: bool,
        does_buildah_work: bool,
        compile_examples: None,
) -> None:
    (scratch_directory / "test_file.txt").write_text("hello world")
    print(scratch_directory)

    (scratch_directory / "test_file.txt").write_text("hello world")
    subprocess.run(command, check=True, cwd=scratch_directory)

    cmd = ["probe", "record", *(["--debug"] if debug else []), "--copy-files", copy_files, *command]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=scratch_directory)

    should_have_copy_files = copy_files in {"eagerly", "lazily"}
    cmd = ["probe", "validate", *(["--should-have-files"] if should_have_copy_files else [])]
    print(shlex.join(cmd))

    # TODO: this doesn't work because we don't capture libraries currently.
    # if should_have_copy_files:
    if False:

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


@pytest.mark.parametrize(
    "command",
    complex_commands.values(),
    ids=complex_commands.keys(),
)
@pytest.mark.timeout(100)
def test_downstream_analyses(
        scratch_directory: pathlib.Path,
        command: list[str],
        does_podman_work: bool,
        does_docker_work: bool,
        does_buildah_work: bool,
) -> None:
    (scratch_directory / "test_file.txt").write_text("hello world")
    print(scratch_directory)

    cmd = ["probe", "record", "--copy-files", "none", *command]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=scratch_directory)

    cmd = ["probe", "export", "debug-text"]
    print(shlex.join(cmd))
    # stdout is huge
    subprocess.run(cmd, check=True, cwd=scratch_directory, stdout=subprocess.DEVNULL)

    cmd = ["probe", "export", "hb-graph", "test.png"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=scratch_directory)

    cmd = ["probe", "export", "dataflow-graph", "test.png"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True, cwd=scratch_directory)


def test_fail(
        scratch_directory: pathlib.Path,
) -> None:
    cmd = ["probe", "record", "--copy-files", "none", str(example_path / "false.exe")]
    proc = subprocess.run(cmd, check=False, cwd=scratch_directory)
    assert proc.returncode != 0
