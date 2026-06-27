import subprocess

def test_cat_random() -> None:
    cmd = ["probe", "record", "--fix-random", "--overwrite", "head", "--bytes=100", "/dev/random"]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    assert proc.stdout.strip() == b"\0" * 100


def test_clock() -> None:
    cmd = ["probe", "record", "--fix-random", "--overwrite", "date", "--utc", "--iso-8601=sec"]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    assert proc.stdout == b"1970-01-01T00:00:00+00:00\n"


def test_py_rand() -> None:
    cmd = ["probe", "record", "--fix-random", "--overwrite", "python", "-c", "import random; print(random.random())"]
    proc0 = subprocess.run(cmd, capture_output=True, check=True)
    proc1 = subprocess.run(cmd, capture_output=True, check=True)
    assert proc0.stdout == proc1.stdout


def test_py_addresses() -> None:
    cmd = ["probe", "record", "--fix-random", "--overwrite", "python", "-c", "print(id(object()))"]
    proc0 = subprocess.run(cmd, capture_output=True, check=True)
    proc1 = subprocess.run(cmd, capture_output=True, check=True)
    assert proc0.stdout == proc1.stdout
