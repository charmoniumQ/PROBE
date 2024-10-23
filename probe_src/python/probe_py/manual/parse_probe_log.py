from __future__ import annotations
import dataclasses
import pathlib
import typing
import json
import tarfile
import tempfile
import contextlib
from ..generated import ops
from .types import ProbeLog, ProbeOptions, Inode, InodeVersion, Pid, ExecNo, Tid, Op, Host


@contextlib.contextmanager
def parse_probe_log_ctx(probe_log: pathlib.Path) -> typing.Iterator[ProbeLog]:
    """Parse probe log

    In this contextmanager, copied_files are extracted onto the disk.

    """
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)

        with tarfile.open(probe_log, mode="r") as tar:
            tar.extractall(tmpdir, filter="data")

        copy_files = (tmpdir / "info" / "copy_files").exists()

        host_name, host_id = (tmpdir / "info"/ "host").read_text().split()
        host = Host(host_name, int(host_id, 16))

        inodes = dict()
        if copy_files and (tmpdir / "inodes").exists():
            for copied_file in (tmpdir / "inodes").iterdir():
                device_major, device_minor, inode_str, mtime_sec, mtime_nsec, size = copied_file.name.split("-")
                inode = Inode(host, int(device_major, 16), int(device_minor, 16), int(inode_str, 16))
                inode_version = InodeVersion(inode, int(mtime_sec, 16), int(mtime_nsec, 16), int(size, 16))
                inodes[inode_version] = copied_file

        processes = dict[Pid, dict[ExecNo, dict[Tid, typing.Sequence[Op]]]]()
        for pid_dir in (tmpdir / "pids").iterdir():
            pid = Pid(pid_dir.name)
            for epoch_dir in pid_dir.iterdir():
                exec_no = ExecNo(epoch_dir.name)
                for tid_file in epoch_dir.iterdir():
                    tid = Tid(tid_file.name)
                    jsonlines = tid_file.read_text().strip().split("\n")
                    ops = [
                        json.loads(line, object_hook=op_hook)
                        for line in jsonlines
                    ]
                    processes.setdefault(pid, {}).setdefault(exec_no, {})[tid] = ops

        yield ProbeLog(
            processes,
            inodes,
            ProbeOptions(
                copy_files=copy_files,
            ),
        )


def parse_probe_log(
        probe_log_path: pathlib.Path,
) -> ProbeLog:
    """Parse probe log.

    Unlike parse_probe_ctx, the copied_files will not be accessible.
    """
    with parse_probe_log_ctx(probe_log_path) as probe_log:
        return dataclasses.replace(probe_log, copied_files={})


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
