
import typing
import json
import tarfile
import subprocess
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

    return ops.__dict__[snake_case_to_pascal(ty)](**json_map)

def snake_case_to_pascal(input: str) -> str:
    ret: str = ""
    prior_underscore: bool = True
    for ch in input:
        if ch == '_':
            prior_underscore = True
            continue
        if prior_underscore:
            ret += ch.upper()
        else:
            ret += ch
        prior_underscore = False

    return ret
