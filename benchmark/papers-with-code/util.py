import typing
import pathlib
import subprocess
import tarfile
import collections.abc
import itertools
import heapq


_FuncParams = typing.ParamSpec("_FuncParams")
_T = typing.TypeVar("_T")
_U = typing.TypeVar("_U")
_V = typing.TypeVar("_V")
_T_contra = typing.TypeVar("_T_contra", contravariant=True)


class SupportsDunderLT(typing.Protocol[_T_contra]):
    def __lt__(self, other: _T_contra, /) -> bool: ...
class SupportsDunderGT(typing.Protocol[_T_contra]):
    def __gt__(self, other: _T_contra, /) -> bool: ...


SupportsRichComparison: typing.TypeAlias = SupportsDunderLT[typing.Any] | SupportsDunderGT[typing.Any]
SupportsRichComparisonT = typing.TypeVar("SupportsRichComparisonT", bound=SupportsRichComparison)  # noqa: Y001


def identity(elem: _T) -> _T:
    return elem


def topk(
        k: int,
        iterable: collections.abc.Iterable[_T],
        key: typing.Callable[[_T], SupportsRichComparisonT] = identity, # type: ignore
) -> list[_T]:
    ret: list[tuple[SupportsRichComparisonT, _T]] = []
    for elem in iterable:
        if len(ret) < k:
            heapq.heappush(ret, (key(elem), elem))
        else:
            heapq.heappushpop(ret, (key(elem), elem))
            assert len(ret) == k
    return [elem for _, elem in ret]


def groupby_dict(
        data: collections.abc.Iterable[_T],
        key_func: typing.Callable[[_T], _V],
        value_func: typing.Callable[[_T], _U],
) -> typing.Mapping[_V, typing.Sequence[_U]]:
    ret: dict[_V, list[_U]] = {}
    for key, group in itertools.groupby(data, key_func):
        ret.setdefault(key, []).extend(map(value_func, group))
    return ret


def get_file_type_of_bytes(content: bytes) -> str:
    return subprocess.run(
        ["file", "--brief", "--mime-type", "-"],
        capture_output=True,
        input=content,
    ).stdout.decode().strip()


def relative_resolve(arg: pathlib.Path) -> pathlib.Path:
    """Resolves ...s in arg, but keeps it relative"""
    return arg.resolve().relative_to(pathlib.Path().resolve())


def tarfile_follow_links(
        tarfile_obj: tarfile.TarFile,
        tarinfo: str | tarfile.TarInfo,
) -> tarfile.TarInfo:
    if isinstance(tarinfo, str):
        tarinfo = tarfile_obj.getmember(tarinfo)
        assert tarinfo
    if tarinfo.issym():
        # For symbolic links (SYMTYPE), the linkname is relative to the directory that contains the link.
        directory = pathlib.Path(tarinfo.name).parent
        relative_path = relative_resolve(directory / tarinfo.linkname)
        return tarfile_follow_links(tarfile_obj, str(relative_path))
    elif tarinfo.islnk():
        # For hard links (LNKTYPE), the linkname is relative to the root of the archive.
        return tarfile_follow_links(tarfile_obj, tarinfo.linkname)
    else:
        return tarinfo
