import shlex
import os
import pathlib
import tempfile
import subprocess
import shutil


pwd = pathlib.Path().resolve()


def run_command_with_prov(cmd: tuple[str, ...]) -> tuple[str, ...]:
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        print("Executing: " + shlex.join(cmd))
        subprocess.run(
            cmd,
            env={
                **os.environ,
                "LD_PRELOAD": f"{pwd}/libprov.so",
                "PROV_LOG_DIR": str(tmpdir),
            },
            check=True,
            capture_output=False,
        )
        output = []
        for child in sorted(tmpdir.iterdir()):
            print(child)
            for line in child.read_text().split("\n"):
                if line:
                    print(line.strip())
                    output.append(line)
        return tuple(output)


def test_head() -> None:
    prov_cmds = run_command_with_prov(("head", "flake.nix"))
    print(prov_cmds[0])
    assert f"OpenRead 3 -1 {pwd}/flake.nix\0" in prov_cmds


def test_shell() -> None:
    prov_cmds = run_command_with_prov(("bash", "-c", "head flake.nix"))
    head = pathlib.Path(shutil.which("head")).resolve()
    assert f"Execute -1 -1 {head}\0" in prov_cmds
    assert f"OpenRead 3 -1 {pwd}/flake.nix\0" in prov_cmds


def test_chdir() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        file = pathlib.Path(tmpdir) / "flake.nix"
        file.write_text("hello\n")
        prov_cmds = run_command_with_prov(("bash", "-c", f"head flake.nix; cd {tmpdir}; head flake.nix"))
    assert f"OpenRead 3 -1 {pwd}/flake.nix\0" in prov_cmds
    assert f"OpenRead 3 -1 {tmpdir}/flake.nix\0" in prov_cmds


if __name__ == "__main__":
    test_head()
    test_shell()
