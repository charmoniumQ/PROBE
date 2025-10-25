from __future__ import annotations
import asyncio
import collections.abc
import dataclasses
import heapq
import itertools
import pathlib
import shlex
import subprocess
import tarfile
import textwrap
import typing
import aioconsole


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


async def async_subprocess_run(
    cmd: collections.abc.Iterable[str],
    hide_output: bool = True,
) -> CalledProcess:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if hide_output:
        stdout, stderr = await proc.communicate()
    else:
        block_size = 1024
        _, stdout_stream = await aioconsole.get_standard_streams(use_stderr=False)
        _, stderr_stream = await aioconsole.get_standard_streams(use_stderr=True)
        async def stream_output(stream: asyncio.StreamReader, sink: asyncio.StreamWriter) -> list[bytes]:
            chunks = []
            while True:
                chunk = await stream.read(block_size)
                if chunk:
                    chunks.append(chunk)
                    sink.write(chunk)
                    await sink.drain()
                else:
                    sink.write_eof()
                    return chunks
        assert proc.stdout and proc.stderr
        stdout_chunks, stderr_chunks = await asyncio.gather(
            stream_output(proc.stdout, stdout_stream),
            stream_output(proc.stderr, stderr_stream),
        )
        await proc.wait()
        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)
    if proc.returncode == 0:
        return CalledProcess(proc.returncode, stdout, stderr)
    else:
        raise CalledProcessError(cmd, stdout, stderr)


@dataclasses.dataclass
class CalledProcess:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclasses.dataclass
class CalledProcessError(Exception):
    cmd: collections.abc.Iterable[str]
    stdout: bytes
    stderr: bytes

    def __str__(self) -> str:
        return "\n".join([
            "$ " + shlex.join(self.cmd),
            "stdout:",
            textwrap.indent(
                self.stdout.decode(errors="backslashreplace"),
                "  ",
            ),
            "stderr:",
            textwrap.indent(
                self.stderr.decode(errors="backslashreplace"),
                "  ",
            ),
        ])
