#!/usr/bin/env python

import sys
import pathlib

file = pathlib.Path(sys.argv[1])
text = file.read_text()
for bad, good in zip(sys.argv[2::2], sys.argv[3::2]):
    text = text.replace(bad, good)
file.write_text(text)
