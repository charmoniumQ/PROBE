import collections
import getpass
import grp
import itertools
import multiprocessing
import os
import pathlib
import tarfile
import time
import typing
import msgspec


_T = typing.TypeVar("_T")
_U = typing.TypeVar("_U")
_V = typing.TypeVar("_V")
_ParamSpec = typing.ParamSpec("_ParamSpec")


def get_umask() -> int:
    old_umask = os.umask(0o644)
    os.umask(old_umask)
    return old_umask


def default_tarinfo(path: pathlib.Path | str) -> tarfile.TarInfo:
    return tarfile.TarInfo(name=str(path)).replace(
        mtime=int(time.time()),
        mode=get_umask(),
        uid=os.getuid(),
        gid=os.getgid(),
        uname=getpass.getuser(),
        gname=grp.getgrgid(os.getgid()).gr_name,
    )


def filter_relative_to(path: pathlib.Path) -> typing.Callable[[tarfile.TarInfo], tarfile.TarInfo]:
    def filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
        member_path = pathlib.Path(member.name)
        return member.replace(name=str(member_path.relative_to(path)))
    return filter


def groupby_dict(
        data: typing.Iterable[_T],
        key_func: typing.Callable[[_T], _V],
        value_func: typing.Callable[[_T], _U] = typing.cast(typing.Callable[[_T], _U], lambda x: x),
) -> typing.Mapping[_V, typing.Sequence[_U]]:
    ret: dict[_V, list[_U]] = {}
    for key, group in itertools.groupby(data, key_func):
        ret.setdefault(key, []).extend(map(value_func, group))
    return ret


def duplicates(
        elements: typing.Iterable[_T],
        mapper: typing.Callable[[_T], _U]
) -> typing.Sequence[tuple[_U, typing.Sequence[_T]]]:
    grouped: typing.Mapping[_U, typing.Sequence[_T]] = groupby_dict(elements, mapper)
    return [
        (key, elements)
        for key, elements in grouped.items()
        if len(elements) > 1
    ]


def decode_nested_object(
        obj: typing.Any,
) -> typing.Any:
    """Converts the bytes in a nested dict to a string"""
    if isinstance(obj, dict):
        return {
            decode_nested_object(key): decode_nested_object(value)
            for key, value in obj.items()
        }
    elif isinstance(obj, msgspec.Struct):
        return decode_nested_object(msgspec.structs.asdict(obj))
    elif isinstance(obj, pathlib.Path):
        return str(obj)
    elif isinstance(obj, (set, list, tuple)):
        return [
            decode_nested_object(elem)
            for elem in obj
        ]
    elif isinstance(obj, bytes):
        return obj.decode(errors="surrogateescape")
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        raise TypeError(f"{type(obj)}: {obj}")


class Comparable(typing.Protocol):
    """Protocol for annotating comparable types."""

    def __lt__(self, other: typing.Self, /) -> bool:
        ...


def is_main_process() -> bool:
    return multiprocessing.parent_process() is None


def raise_(exception: Exception) -> typing.NoReturn:
    raise exception


def ancestors(path: pathlib.Path) -> collections.abc.Iterator[pathlib.Path]:
    while True:
        yield path
        if path.parent == path:
            return
        path = path.parent

