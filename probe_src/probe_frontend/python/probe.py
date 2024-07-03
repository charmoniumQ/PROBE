
import typing
import json
import tarfile
from . import ops

OpTable = typing.Mapping[int, typing.Mapping[int, typing.Mapping[int, typing.List[ops.Op]]]]

def load_log(path: str) -> OpTable:
    ret: dict[int, dict[int, dict[int, list[ops.Op]]]] = {}

    tar = tarfile.open(path, mode='r')

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
        if not pid in ret:
            ret[pid] = {}
        if not epoch in ret[pid]:
            ret[pid][epoch] = {}
        if not tid in ret[pid][epoch]:
            ret[pid][epoch][tid] = []

        # extract file contents as byte buffer
        file = tar.extractfile(item)
        if file is None:
            raise IOError("Unable to read jsonlines from probe log")

        # read, split, comprehend, deserialize, extend
        jsonlines = file.read().strip().split(b"\n")
        ops = [json.loads(x, object_hook=op_hook) for x in jsonlines]
        ret[pid][epoch][tid].extend(ops)

    return ret 

def op_hook(json_map: typing.Dict[str, typing.Any]):
    ty: str = json_map["_type"]
    json_map.pop("_type")

    constructor = ops.__dict__[ty]

    for ident, ty in constructor.__annotations__.items():
        if ty == "bytes" and ident in json_map:
            json_map[ident] = bytes(json_map[ident])

    return constructor(**json_map)
