import shlex
import subprocess


def test_handoff() -> None:
    cmd = ["probe", "py", "validate", "--help"]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True)
