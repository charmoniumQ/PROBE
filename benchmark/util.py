import typing
import itertools
import os
import json
import sys
import dataclasses
import random
import bitmath
import tempfile
import contextlib
import pathlib
import shlex
import shutil
import subprocess
import urllib.request
from collections.abc import Sequence, Mapping, Iterator, Iterable
from typing import Callable, TypeVar, Any, TypeAlias, cast, Hashable
import rich
import rich.table
import rich.progress
import tqdm


console = rich.console.Console()


def download(output: pathlib.Path, url: str) -> None:
    class DownloadProgressBar(tqdm.tqdm):
        def update_to(self, b=1, bsize=1, tsize=None):
            if tsize is not None:
                self.total = tsize
            self.update(b * bsize - self.n)
    output.parent.mkdir(parents=True, exist_ok=True)
    with DownloadProgressBar(unit='B', unit_scale=True,
                             miniters=1, desc=url.split('/')[-1]) as t:
        console.print(url)
        urllib.request.urlretrieve(url, filename=output, reporthook=t.update_to)


def terminate_or_kill(proc: subprocess.Popen[bytes], timeout: int) -> None:
    proc.terminate()
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


CmdArg: TypeAlias = os.PathLike[str] | os.PathLike[bytes] | str | bytes


def cmd_arg(arg: CmdArg) -> bytes:
    if isinstance(arg, os.PathLike):
        return cmd_arg(os.fspath(arg))
    elif isinstance(arg, str):
        return arg.encode()
    elif isinstance(arg, bytes):
        return arg
    else:
        raise TypeError(f"{arg}: {type(arg)} is not convertable to a cmd arg")


def run_all(*cmds: Sequence[CmdArg]) -> tuple[bytes, ...]:
    return b"sh", b"-c", b" && ".join(shlex.join(map(lambda arg: cmd_arg(arg).decode(), cmd)).encode() for cmd in cmds)


def env_command(
        env: Mapping[CmdArg, CmdArg] = {},
        cwd: None | pathlib.Path = None,
        clear_env: bool = False,
        cmd: Sequence[CmdArg] = (),
) -> Sequence[bytes]:
    if not env and not cwd and not clear_env:
        return tuple(map(cmd_arg, cmd))
    else:
        return (
            b"env",
            *((b"--ignore-environment",) if clear_env else ()),
            *((b"--chdir", cmd_arg(cwd)) if cwd is not None else ()),
            *tuple(cmd_arg(key) + b"=" + cmd_arg(val) for key, val in env.items()),
            *map(cmd_arg, cmd),
        )


@contextlib.contextmanager
def gen_temp_dir() -> Iterator[pathlib.Path]:
    with tempfile.TemporaryDirectory() as tempfile_str:
        yield pathlib.Path(tempfile_str)


def move_children(src: pathlib.Path, dst: pathlib.Path) -> None:
    for child in src.iterdir():
        if (dst / child.name).exists():
            if (dst / child.name).is_dir():
                shutil.rmtree(dst / child.name)
            else:
                (dst / child.name).unlink()
        shutil.move(src / child.name, dst / child.name)


def delete_children(dir: pathlib.Path) -> None:
    for child in dir.iterdir():
        if child.is_symlink():
            child.unlink()
        elif child.is_dir():
            delete_children(child)
            os.rmdir(child)
        else:
            child.unlink()


def hardlink_children(src: pathlib.Path, dst: pathlib.Path) -> None:
    for child in src.iterdir():
        if child.is_dir():
            (dst / child.name).mkdir()
            hardlink_children(src / child.name, dst / child.name)
        else:
            (dst / child.name).hardlink_to(src / child.name)


_T = TypeVar("_T")
_V = TypeVar("_V")
_U = TypeVar("_U")


def shuffle(seed: int, lst: Sequence[_T]) -> Sequence[_T]:
    lst2 = list(lst)
    random.Random(seed).shuffle(lst2)
    return lst2


def expect_type(typ: type[_T], data: Any) -> _T:
    if not isinstance(data, typ):
        raise TypeError(f"Expected type {typ} for {data}")
    # mypy considers this a redundant cast.
    # Apparently they're pretty smart.
    # return cast(_T, data)
    return data


def first(pair: tuple[_T, _V]) -> _T:
    return pair[0]


def identity(x: _T) -> _T:
    return x


def groupby_dict(
        data: Iterable[_T],
        key_func: Callable[[_T], _V],
        value_func: Callable[[_T], _U],
) -> Mapping[_V, Sequence[_U]]:
    ret: dict[_V, list[_U]] = {}
    for key, group in itertools.groupby(data, key_func):
        ret.setdefault(key, []).extend(map(value_func, group))
    return ret


def confidence_interval(data: Any, confidence_level: float, seed: int = 0) -> tuple[float, float]:
    import scipy  # type: ignore
    import numpy
    bootstrap = scipy.stats.bootstrap(
        [data],
        confidence_level=confidence_level,
        statistic=numpy.mean,
        vectorized=True,
        random_state=numpy.random.RandomState(seed),
    )
    return (bootstrap.confidence_interval.low, bootstrap.confidence_interval.high)


@dataclasses.dataclass
class SubprocessError(Exception):
    cmd: Sequence[CmdArg]
    returncode: int
    stdout: str
    stderr: str
    env: Mapping[str, str]
    cwd: pathlib.Path | None = None

    def __init__(
        self,
        cmd: Sequence[CmdArg],
        env: Mapping[CmdArg, CmdArg],
        cwd: pathlib.Path | None,
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.cmd = cmd
        self.env = {cmd_arg(key).decode(): cmd_arg(val).decode() for key, val in env.items()}
        self.cwd = cwd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self) -> str:
        args = env_command(
            env={key: val for key, val in self.env.items()},
            cwd=self.cwd,
            clear_env=True,
            cmd=self.cmd,
        )
        arg_strs = []
        for arg in args:
            try:
                arg_str = to_str(arg)
            except Exception as exc:
                console.print(f"{exc} while converting {arg!r}")
                arg_str = "<unk>"
            arg_strs.append(arg_str)
        args_joined = shlex.join(arg_strs)
        return f"\n$ {args_joined}\n{self.stdout}\n\n{self.stderr}\n\n$ echo $?\n{self.returncode}"


def to_str(thing: Any) -> str:
    if isinstance(thing, str):
        return thing
    elif isinstance(thing, bytes):
        return thing.decode(errors="backslashreplace")
    else:
        return str(thing)


def check_returncode(
        proc: subprocess.CompletedProcess[_T],
        env: Mapping[CmdArg, CmdArg] | Mapping[str, CmdArg] = cast(Mapping[str, CmdArg], {}),
        cwd: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[_T]:
    if proc.returncode != 0:
        raise SubprocessError(
            cmd=proc.args,
            env={key: val for key, val in env.items()},
            cwd=cwd,
            returncode=proc.returncode,
            stdout=to_str(proc.stdout),
            stderr=to_str(proc.stderr),
        )
    return proc


def merge_dicts(dcts: Iterable[Mapping[_T, _V]]) -> dict[_T, _V]:
    return dict(itertools.chain.from_iterable(dct.items() for dct in dcts))


def merge_env_vars(*envs: Mapping[str, str]) -> Mapping[str, str]:
    result_env: dict[str, str] = {}
    for env in envs:
        for key, value in env.items():
            pre_existing_value = result_env.get(key, None)
            if pre_existing_value:
                result_env[key] = pre_existing_value + ":" + value
            else:
                result_env[key] = value
    return result_env


def remove_keys(dct: Mapping[_T, _V], keys: set[_T]) -> Mapping[_T, _V]:
    return {key: val for key, val in dct.items() if key not in keys}


def flatten1(it: Iterable[Iterable[_T]]) -> Iterable[_T]:
    for elem in it:
        yield from elem


def all_unique(it: Iterable[Hashable]) -> bool:
    lst = list(it)
    return len(set(lst)) == list(lst)


def n_unique(it: Iterable[Hashable]) -> int:
    return len(set(it))


_system_nix_path = shutil.which("nix")
if _system_nix_path is None:
    raise ValueError("Please add `nix` to the $PATH")
_project_nix_path = check_returncode(subprocess.run(
    [_system_nix_path, "shell", ".#which", ".#nix", "--command", "which", "nix"],
    env=cast(Mapping[str, str], {}),
    capture_output=True,
    text=True,
    check=False,
)).stdout.strip()
NIX_BIN_PATH = pathlib.Path(_project_nix_path)


def get_nix_env(packages: list[str]) -> Mapping[str, str]:
    if packages:
        return json.loads(check_returncode(subprocess.run(
            [NIX_BIN_PATH, "shell", *packages, "--command", sys.executable, "-c", "import os, json; print(json.dumps(dict(**os.environ)))"],
            env=cast(Mapping[str, str], {}),
            capture_output=True,
            text=True,
            check=False,
        )).stdout)
    else:
        return {}


def raise_(exception: Exception) -> typing.NoReturn:
    raise exception


def dir_size(dir: pathlib.Path) -> int:
    return sum([
        dir_size(child) if child.is_dir() else child.stat().st_size
        for child in dir.iterdir()
    ])


def print_rich_table(
        title: str | None,
        columns: typing.Sequence[str],
        rows: typing.Sequence[typing.Sequence[typing.Any]],
) -> rich.table.Table:
    """Functional wrapper around rich.table.Table"""
    table = rich.table.Table(*columns, title=title)
    for row in rows:
        table.add_row(*[
            cell if isinstance(cell, str) else str(cell)
            for cell in row
        ])
    console.print(table)
    return table


progress = rich.progress.Progress(
    rich.progress.TextColumn("[progress.description]{task.description}"),
    rich.progress.BarColumn(),
    rich.progress.TaskProgressColumn(show_speed=True),
    rich.progress.TimeElapsedColumn(),
    rich.progress.TimeRemainingColumn(),
    rich.progress.MofNCompleteColumn(),
    console=console,
    speed_estimate_period=60 * 60, # in seconds
)


_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsDunderLT(typing.Protocol[_T_contra]):
    def __lt__(self, __other: _T_contra) -> bool: ...


class SupportsDunderGT(typing.Protocol[_T_contra]):
    def __gt__(self, __other: _T_contra) -> bool: ...


SupportsRichComparison: typing.TypeAlias = SupportsDunderLT[typing.Any] | SupportsDunderGT[typing.Any]
SupportsRichComparisonT = typing.TypeVar("SupportsRichComparisonT", bound=SupportsRichComparison)



def fmt_bytes(bm: bitmath.Bitmath | int, d: int = 0) -> str:
    if isinstance(bm, int):
        return fmt_bytes(bitmath.Byte(bm))
    elif isinstance(bm, bitmath.Bitmath):
        return bm.best_prefix().format(f"{{value:.{d}f}}{{unit}}")
    else:
        raise TypeError(f"{bm}: {type(bm).__name__}")


def last_sentinel(it: Iterable[_T]) -> Iterator[tuple[bool, _T]]:
    is_first = True
    for elem in it:
        if not is_first:
            yield False, tmp
        tmp = elem
        is_first = False
    yield True, tmp
