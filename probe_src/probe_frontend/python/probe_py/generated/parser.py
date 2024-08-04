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
class ProvLog:
    processes: typing.Mapping[int, ProcessProvLog]

def parse_probe_log(probe_log: pathlib.Path) -> ProvLog:
    op_map: typing.Dict[int, typing.Dict[int, typing.Dict[int, ThreadProvLog]]] = {}

    tar = tarfile.open(probe_log, mode='r')

    for item in tar:
        # items with size zero are directories in the tarball
        if item.size == 0:
            continue

        # extract and name the hierarchy components
        parts = item.name.split("/")
        if len(parts) != 3:
            raise ValueError("malformed probe log")
        pid: int = int(parts[0])
        epoch: int = int(parts[1])
        tid: int = int(parts[2])

        # ensure necessary dict objects have been created
        if pid not in op_map:
            op_map[pid] = {}
        if epoch not in op_map[pid]:
            op_map[pid][epoch] = {}

        # extract file contents as byte buffer
        file = tar.extractfile(item)
        if file is None:
            raise IOError("Unable to read jsonlines from probe log")

        # read, split, comprehend, deserialize, extend
        jsonlines = file.read().strip().split(b"\n")
        ops = ThreadProvLog(tid, [json.loads(x, object_hook=op_hook) for x in jsonlines])
        op_map[pid][epoch][tid] = ops

    return ProvLog({
        pid: ProcessProvLog(
            pid,
            {
                epoch: ExecEpochProvLog(epoch, threads)
                for epoch, threads in epochs.items()
            },
        )
        for pid, epochs in op_map.items()
    })

def op_hook(json_map: typing.Dict[str, typing.Any]) -> typing.Any:
    ty: str = json_map["_type"]
    json_map.pop("_type")

    constructor = ops.__dict__[ty]

    for ident, ty in constructor.__annotations__.items():
        if ty == "bytes" and ident in json_map:
            json_map[ident] = bytes(json_map[ident])

    return constructor(**json_map)
