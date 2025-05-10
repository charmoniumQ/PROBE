from __future__ import annotations
import dataclasses
import pathlib
import typing
import json
import tarfile
import tempfile
import contextlib
import numpy
from . import ops
from .ptypes import ProbeLog, ProbeOptions, Inode, InodeVersion, Pid, ExecNo, Tid, Host, KernelThread, Process, Exec, Device


def iv_from_file_name(host: Host, name: str) -> InodeVersion:
    # See `libprobe/src/prov_utils.c:path_to_id_string()`
    array = [
        int(segment, 16)
        for segment in name.split("-")
    ]
    assert len(array) == 6
    return InodeVersion(
        # TODO: use the correct host
        Inode(host, Device(array[0], array[1]), array[2]),
        numpy.datetime64(array[3] * int(1e9) + array[4], "ns"),
        array[5],
    )


@contextlib.contextmanager
def parse_probe_log_ctx(path_to_probe_log: pathlib.Path) -> typing.Iterator[ProbeLog]:
    """Parse probe log

    In this contextmanager, copied_files are extracted onto the disk.

    """
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        with tarfile.open(path_to_probe_log, mode="r") as tar:
            tar.extractall(tmpdir, filter="data")
        host = Host.localhost()
        inodes = {
            InodeVersion.from_id_string(file.name): file
            for file in (tmpdir / "inodes").iterdir()
        } if (tmpdir / "inodes").exists() else {}

        processes = dict[Pid, Process]()
        for pid_dir in (tmpdir / "pids").iterdir():
            pid = Pid(pid_dir.name)
            execs = {}
            for epoch_dir in pid_dir.iterdir():
                exec_no = ExecNo(epoch_dir.name)
                threads = {}
                for tid_file in epoch_dir.iterdir():
                    tid = Tid(tid_file.name)
                    jsonlines = tid_file.read_text().strip().split("\n")
                    ops_list = [
                        json.loads(line, object_hook=_op_hook)
                        for line in jsonlines
                    ]
                    threads[tid] = KernelThread(tid, ops_list)
                execs[exec_no] = Exec(exec_no, threads)
            processes[pid] = Process(pid, execs)

        options = json.loads((tmpdir / "options.json").read_bytes())

        yield ProbeLog(
            processes,
            inodes,
            ProbeOptions(
                copy_files=options["copy_files"] != 0,
                parent_of_root=options["parent_of_root"],
            ),
            host,
        )


def parse_probe_log(
        path_to_probe_log: pathlib.Path,
) -> ProbeLog:
    """Parse probe log.

    Unlike parse_probe_ctx, the copied_files will not be accessible.
    """
    with parse_probe_log_ctx(path_to_probe_log) as probe_log:
        return dataclasses.replace(
            probe_log,
            copied_files={},
            probe_options=dataclasses.replace(probe_log.probe_options, copy_files=False),
        )


def _op_hook(json_map: typing.Dict[str, typing.Any]) -> typing.Any:
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
