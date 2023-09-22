import itertools
import os
import dataclasses
import random
import tempfile
import contextlib
import pathlib
import shlex
import shutil
import subprocess
import urllib.request
from collections.abc import Sequence, Mapping, Iterator, Iterable
from typing import Callable, TypeVar, Any, TypeAlias, cast


def download(output: pathlib.Path, url: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as src_fobj:
        with output.open("wb") as dst_fobj:
            shutil.copyfileobj(src_fobj, dst_fobj)


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


def run_all(*cmds: Sequence[CmdArg]) -> Sequence[bytes]:
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
        if child.is_dir():
            shutil.rmtree(child)
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


def shuffle(prng: random.Random, lst: Sequence[_T]) -> Sequence[_T]:
    lst2 = list(lst)
    prng.shuffle(lst2)
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


def groupby_dict(
        data: Iterable[_T],
        key_func: Callable[[_T], _V],
        value_func: Callable[[_T], _U],
) -> Mapping[_V, Sequence[_U]]:
    ret: dict[_V, list[_U]] = {}
    for key, group in itertools.groupby(data, key_func):
        ret.setdefault(key, []).extend(map(value_func, group))
    return ret


import scipy  # type: ignore
import numpy
def confidence_interval(data: Any, confidence_level: float, seed: int = 0) -> tuple[float, float]:
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
    env: Mapping[CmdArg, CmdArg]
    cwd: pathlib.Path | None
    returncode: int
    stdout: str
    stderr: str

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
        self.env = env
        self.cwd = cwd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self) -> str:
        command = shlex.join(map(to_str, env_command(
            env=self.env,
            cwd=self.cwd,
            clear_env= False,
            cmd=self.cmd,
        )))
        return f"\n$ {command}\n{self.stdout}\n\n{self.stderr}\n\n$ echo $?\n{self.returncode}"


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
            env=dict(**env),
            cwd=cwd,
            returncode=proc.returncode,
            stdout=to_str(proc.stdout),
            stderr=to_str(proc.stderr),
        )
    return proc


def merge_env_vars(*envs: Mapping[CmdArg, CmdArg]) -> Mapping[CmdArg, CmdArg]:
    result_env: dict[str, str] = {}
    for env in envs:
        for key, value in env.items():
            pre_existing_value = result_env.get(to_str(key), None)
            if pre_existing_value:
                result_env[to_str(key)] = pre_existing_value + ":" + to_str(value)
            else:
                result_env[to_str(key)] = to_str(value)
    return cast(Mapping[CmdArg, CmdArg], result_env)
