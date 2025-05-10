import pathlib
import re
import sys


for file in sys.argv[1:]:
    for line_no, line in enumerate(pathlib.Path(file).read_text().strip().splitlines()):
        for fn in pathlib.Path("generated/libc_fns.csv").read_text().strip().splitlines():
            if matchy := re.search("\b" + fn + "\b", line):
                print(f"(Unwrapped) {fn} found at {file}:{line_no + 1}")
