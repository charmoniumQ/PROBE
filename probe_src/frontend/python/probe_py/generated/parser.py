import pathlib
import typing
import json
import tarfile
from dataclasses import dataclass
from . import ops

@dataclass(frozen=True)
class ThreadProvLog:
    tid: int
    ops: typing.Sequence[ops.Op]

@dataclass(frozen=True)
class ExecEpochProvLog:
    epoch: int
    threads: typing.Mapping[int, ThreadProvLog]


@dataclass(frozen=True)
class ProcessProvLog:
    pid: int
    exec_epochs: typing.Mapping[int, ExecEpochProvLog]


@dataclass(frozen=True)
class InodeVersionLog:
    device_major: int
    device_minor: int
    inode: int
    tv_sec: int
    tv_nsec: int
    size: int


@dataclass(frozen=True)
class ProvLog:
    processes: typing.Mapping[int, ProcessProvLog]
    inodes: typing.Mapping[InodeVersionLog, bytes]
    has_inodes: bool

def parse_probe_log(probe_log: pathlib.Path) -> ProvLog:
    op_map = dict[int, dict[int, dict[int, ThreadProvLog]]]()
    inodes = dict[InodeVersionLog, bytes]()
    has_inodes = False

    tar = tarfile.open(probe_log, mode='r')

    for item in tar:
        # items with size zero are directories in the tarball
        if item.size == 0:
            continue

        # extract and name the hierarchy components
        parts = item.name.split("/")
        if parts[0] == "info":
            if parts[1] == "copy_files":
                has_inodes = True
        elif parts[0] == "inodes":
            if len(parts) != 2:
                raise RuntimeError("Invalid probe_log")
            file = tar.extractfile(item)
            if file is None:
                raise IOError("Unable to read from probe_log")
            inodes[InodeVersionLog(*[
                int(segment, 16)
                for segment in parts[1].split("-")
            ])] = file.read()
        elif parts[0] == "pids":
            if len(parts) != 4:
                raise RuntimeError("Invalid probe_log")
            pid: int = int(parts[1])
            epoch: int = int(parts[2])
            tid: int = int(parts[3])

            # extract file contents as byte buffer
            file = tar.extractfile(item)
            if file is None:
                raise IOError("Unable to read jsonlines from probe log")

            # read, split, comprehend, deserialize, extend
            jsonlines = file.read().strip().split(b"\n")
            ops = ThreadProvLog(tid, [json.loads(x, object_hook=op_hook) for x in jsonlines])
            op_map.setdefault(pid, {}).setdefault(epoch, {})[tid] = ops

    return ProvLog(
        processes={
            pid: ProcessProvLog(
                pid,
                {
                    epoch: ExecEpochProvLog(epoch, threads)
                    for epoch, threads in epochs.items()
                },
            )
            for pid, epochs in op_map.items()
        },
        inodes=inodes,
        has_inodes=has_inodes,
    )

def op_hook(json_map: typing.Dict[str, typing.Any]) -> typing.Any:
    ty: str = json_map["_type"]
    json_map.pop("_type")

    constructor = ops.__dict__[ty]

    # HACK: convert jsonlines' lists of integers into python byte types
    for ident, ty in constructor.__annotations__.items():
        if ty == "bytes" and ident in json_map:
            json_map[ident] = bytes(json_map[ident])
        if ty == "list[bytes,]" and ident in json_map:
            json_map[ident] = [bytes(x) for x in json_map[ident]]

    return constructor(**json_map)
