import shlex
import os
import pathlib
import tempfile
import subprocess


def run_command_with_prov(cmd: tuple[str, ...]) -> tuple[str, ...]:
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        print("Executing: " + shlex.join(cmd))
        subprocess.run(
            cmd,
            env={
                **os.environ,
                "LD_PRELOAD": "./libprov.so",
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
    assert "OpenRead 3 -1 flake.nix\0" in prov_cmds


def test_shell() -> None:
    prov_cmds = run_command_with_prov(("bash", "-c", "head flake.nix"))
    assert any(
        line.startswith("Execute -1 -1") and line.endswith("bin/head\0")
        for line in prov_cmds
    )
    assert "OpenRead 3 -1 flake.nix\0" in prov_cmds


if __name__ == "__main__":
    test_head()
    test_shell()
