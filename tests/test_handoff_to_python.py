import shlex
import subprocess


def test_handoff() -> None:
    cmd = ["probe", "validate", "--help"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True)
