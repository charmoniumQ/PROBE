from __future__ import annotations
import pathlib
import typing
import json
import tarfile
import tempfile
import contextlib
from . import ops
from .ptypes import ProbeLog, InodeVersionLog, KernelThread, Exec, Process
from dataclasses import replace


@contextlib.contextmanager
def parse_probe_log_ctx(
        path_to_probe_log: pathlib.Path,
) -> typing.Iterator[ProbeLog]:
    """Parse probe log

    In this contextmanager, copied_files are extracted onto the disk.

    """
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        with tarfile.open(path_to_probe_log, mode="r") as tar:
            tar.extractall(tmpdir, filter="data")
        has_inodes = (tmpdir / "info" / "copy_files").exists()
        inodes = {
            InodeVersionLog(*[
                int(segment, 16)
                for segment in file.name.split("-")
            ]): file
            for file in (tmpdir / "inodes").iterdir()
        } if (tmpdir / "inodes").exists() else None

        processes = {}
        for pid_dir in (tmpdir / "pids").iterdir():
            pid = int(pid_dir.name)
            epochs = {}
            for epoch_dir in pid_dir.iterdir():
                epoch = int(epoch_dir.name)
                tids = {}
                for tid_file in epoch_dir.iterdir():
                    tid = int(tid_file.name)
                    # read, split, comprehend, deserialize, extend
                    jsonlines = tid_file.read_text().strip().split("\n")
                    tids[tid] = KernelThread(tid, [json.loads(x, object_hook=op_hook) for x in jsonlines])
                epochs[epoch] = Exec(epoch, tids)
            processes[pid] = Process(pid, epochs)
        yield ProbeLog(processes, inodes, has_inodes)

def parse_probe_log(
        path_to_probe_log: pathlib.Path,
) -> ProbeLog:
    """Parse probe log.

    Unlike parse_probe_ctx, the copied_files will not be accessible.
    """
    with parse_probe_log_ctx(path_to_probe_log) as probe_log:
        return replace(probe_log, has_inodes=False, inodes={})


def op_hook(json_map: typing.Dict[str, typing.Any]) -> typing.Any:
    ty: str = json_map["_type"]
    json_map.pop("_type")

    constructor = ops.__dict__[ty]

    # HACK: convert jsonlines' lists of integers into python byte types
    # This is because json cannot actually represent byte strings, only unicode strings.
    for ident, ty in constructor.__annotations__.items():
        if ty == "bytes" and ident in json_map:
            json_map[ident] = bytes(json_map[ident])
        if ty == "list[bytes,]" and ident in json_map:
            json_map[ident] = [bytes(x) for x in json_map[ident]]

    return constructor(**json_map)
