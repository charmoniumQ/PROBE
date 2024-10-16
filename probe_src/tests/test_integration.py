import shutil
import pathlib
import shlex
import subprocess


project_root = pathlib.Path(__file__).resolve().parent.parent.parent
tmpdir = pathlib.Path(__file__).resolve().parent / "tmp"


def bash(*cmds: str) -> list[str]:
    return ["bash", "-c", shlex.join(cmds).replace(" and ", " && ").replace(" redirect_to ", " > ")]


commands = [
    bash(
        "and",
        *bash(
            *bash("echo", "hi", "redirect_to", "file0"),
            "and",
            *bash("cat", "file0", "file0", "redirect_to", "file1"),
        ),
        "and",
        *bash(
            *bash("cat", "file0", "file1", "redirect_to", "file2"),
            "and",
            *bash("cat", "file0", "file2", "redirect_to", "file3"),
        ),
    ),
    bash(
        "echo",
        "#include <stdio.h>\nint main() {printf(\"hello world\\n\"); return 0; }",
        "redirect_to",
        "test.c",
        "and",
        "gcc",
        "test.c",
        "and",
        "./a.out",
    ),
    ["echo", "hi"],
]

modes = [
    ["probe", "record"],
    ["probe", "record", "--debug"],
    ["probe", "record", "--copy-files"],
]


def test_cmds() -> None:
    for command in commands:
        for mode in modes:
            if tmpdir.exists():
                shutil.rmtree(tmpdir)
            tmpdir.mkdir()
            subprocess.run(
                [*mode, *command],
                check=True,
                cwd=tmpdir,
            )
            subprocess.run(
                ["probe", "validate", *(["--should-have-files"] if "copy-files" in mode else []), "--input", "probe_log"],
                check=True,
                cwd=tmpdir,
            )
