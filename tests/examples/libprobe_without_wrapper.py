#!/usr/bin/env python
from __future__ import annotations
import sys
import subprocess
import pathlib
import tempfile
import enum
import ctypes
import os

USE_GDB = False
LD_DEBUG = "all"

cmd = sys.argv[1]
args = sys.argv[2:]
# subprocess.run(
#     [cmd, *args],
#     check=True,
#     capture_output=False,
# )

if "__file__" in locals():
    proj_root = pathlib.Path(__file__).resolve().parent.parent.parent
else:
    proj_root = pathlib.Path().resolve().parent.parent
libprobe = proj_root / "libprobe/.build/libprobe.dbg.so"
if not libprobe.exists():
    raise RuntimeError(f"Need to build libprobe first; try 'just compile && ls {libprobe!s}'")

probe_dir = pathlib.Path(tempfile.mkdtemp())

# Parsing this header is too annoying
# import pycparser
# libprobe_bindings = pycparser.parse_file("../../libprobe/generated/bindings.h", use_cpp=True)
# process_context_struct = next(
#     item.type
#     for item in bindings_header.ext
#     if  isinstance(item, pycparser.c_ast.Decl)
#         and isinstance(item.type, pycparser.c_ast.Struct)
#         and item.type.name == "ProcessContext"
# )
# print(process_context_struct.decls)


PROBE_PATH_MAX = 4096


class FixedPath(ctypes.Structure):
    _fields_ = [
        ("bytes", ctypes.c_char * PROBE_PATH_MAX),
        ("len", ctypes.c_uint32),
    ]

    @staticmethod
    def new(p: pathlib.Path) -> FixedPath:
        string = str(p.resolve()).encode()
        return FixedPath(
            bytes=string + b"\0",
            len=len(string),
        )


class CopyFilesMode(enum.IntEnum):
    DONT_COPY = 0
    COPY_LAZILY = 1
    COPY_EAGERLY = 2


class ProcessContext(ctypes.Structure):
    _fields_ = [
        ("libprobe_path", FixedPath),
        ("copy_files", ctypes.c_uint32),
    ]

    @staticmethod
    def new(libprobe_path: pathlib.Path, copy_files: CopyFilesMode) -> ProcessContext:
        return ProcessContext(
            libprobe_path=FixedPath.new(libprobe_path),
            copy_files=copy_files.value,
        )

(probe_dir / "pids").mkdir()
(probe_dir / "context").mkdir()
(probe_dir / "inodes").mkdir()
(probe_dir / "process_tree_context").write_bytes(bytearray(ProcessContext.new(
    libprobe_path=libprobe,
    copy_files=CopyFilesMode.DONT_COPY,
)))


print(f"{libprobe=}")
print(f"{probe_dir=}")

if USE_GDB:
    subprocess.run(
        [
            "gdb",
            "--quiet",
            # "--eval-command=set environment LD_DEBUG all",
        f"--eval-command=set environment LD_PRELOAD {libprobe!s}",
        f"--eval-command=set environment PROBE_DIR {probe_dir!s}",
        f"--eval-command=set environment LD_DEBUG {LD_DEBUG}",
        "--eval-command=run",
        "--eval-command=backtrace",
        "--args",
        cmd,
        *args,
        ],
        capture_output=False,
    )
else:
    subprocess.run(
        [cmd, *args],
        check=True,
        capture_output=False,
        env={
            **os.environ,
            "LD_PRELOAD": str(libprobe),
            "PROBE_DIR": str(probe_dir),
            "LD_DEBUG": LD_DEBUG,
        },
    )
