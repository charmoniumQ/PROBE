import shutil
import subprocess


# Mash keyboard sufficiently
nonexistent_command = "eugrhuerhuliaflsd"


def test_probe_nonexistent_command() -> None:
    assert (
        shutil.which(nonexistent_command) is None
    ), "please choose a nonexistent_command"
    proc = subprocess.run(
        ["probe", "record", "-f", nonexistent_command],
        capture_output=True,
        check=False,
    )
    # Rust wrapper catches and warns us of segfaults.
    assert b"SIGSEGV" not in proc.stderr


def test_probe_empty_path() -> None:
    proc = subprocess.run(
        ["probe", "record", "-f", "env", "PATH=", nonexistent_command],
        capture_output=True,
        check=False,
    )
    assert b"SIGSEGV" not in proc.stderr
