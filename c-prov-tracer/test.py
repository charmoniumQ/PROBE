import os
import pathlib
import tempfile
import subprocess


def run_command_with_prov(cmd: tuple[str, ...]) -> tuple[str, ...]:
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        subprocess.run(
            cmd,
            env={
                **os.environ,
                "LD_PRELOAD": "./libprov.so",
                "LIBPROV_DIR": str(tmpdir),
            },
            check=True,
            capture_output=True,
        )
        return tuple(
            line
            for child in sorted(tmpdir.iterdir())
            for line in child.read_text().split("\n")
            if line
        )


def test_head() -> None:
    prov_cmds = run_command_with_prov(("head", "flake.nix"))
    print(prov_cmds)
    assert "open" in prov_cmds


def test_shell() -> None:
    prov_cmds = run_command_with_prov(("bash", "-c", "head flake.nix"))
    print(prov_cmds)
    assert "execve" in prov_cmds


if __name__ == "__main__":
    test_head()
    test_shell()
