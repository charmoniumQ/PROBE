from __future__ import annotations
import pathlib
import dataclasses
import os
import contextlib
import signal
import warnings
import types
from pathlib import Path
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Callable, TypeAlias, Union
from benchexec.runexecutor import RunExecutor  # type: ignore
from benchexec import container  # type: ignore
from util import gen_temp_dir, CmdArg, cmd_arg


os.environ["LIBSECCOMP"] = str(
    Path(__file__).resolve().parent / "result/lib/libseccomp.so.2"
)


Signal: TypeAlias = int
SignalCatcher: TypeAlias = Union[
    Callable[[Signal, types.FrameType | None], Any],
    int,
    signal.Handlers,
    None,
]


@contextlib.contextmanager
def catch_signals(
    signal_catchers: Mapping[signal.Signals, SignalCatcher]
) -> Iterator[None]:
    old_signal_catchers: dict[signal.Signals, SignalCatcher] = {}
    for signal_num, new_catcher in signal_catchers.items():
        old_catcher = signal.signal(signal_num, new_catcher)
        old_signal_catchers[signal_num] = old_catcher
    yield
    for signal_num, old_catcher in old_signal_catchers.items():
        signal.signal(signal_num, old_catcher)


@contextlib.contextmanager
def runexec_catch_signals(run_executor: RunExecutor) -> Iterator[None]:
    caught_signal_number: None | signal.Signals = None

    def run_executor_stop(signal_number: Signal, _: types.FrameType | None) -> None:
        warnings.warn(f"In signal catcher for {signal_number}")
        run_executor.stop()

    with catch_signals(
        {
            signal.SIGTERM: run_executor_stop,
            signal.SIGQUIT: run_executor_stop,
            signal.SIGINT: run_executor_stop,
        }
    ):
        yield
    if caught_signal_number is not None:
        raise InterruptedError(f"Caught signal {caught_signal_number}")


@dataclasses.dataclass
class RunexecStats:
    exitcode: int
    walltime: float
    cputime: float
    memory: int
    blkio_read: int | None
    blkio_write: int | None
    cpuenergy: float | None
    termination_reason: str | None
    success: bool
    stdout: bytes
    stderr: bytes

    @staticmethod
    def create(result: Mapping[str, Any], stdout: bytes, stderr: bytes) -> RunexecStats:
        keys = set(
            "walltime cputime memory blkio_read blkio_write cpuenergy".split(" ")
        )
        attrs = {key: result.get(key, None) for key in keys}
        attrs["termination_reason"] = result.get("terminationreason", None)
        attrs["exitcode"] = result["exitcode"].raw
        attrs["success"] = attrs["exitcode"] == 0
        attrs["stdout"] = stdout
        attrs["stderr"] = stderr
        return RunexecStats(**attrs)


# https://github.com/sosy-lab/benchexec/blob/2c56e08d5f0f44b3073f9c82a6c5f166a12b45e7/benchexec/containerexecutor.py#L30
class DirMode:
    "Typesafe enum, wrapping benchexec.container.DIR_*."
    READ_ONLY: object = container.DIR_READ_ONLY
    HIDDEN: object = container.DIR_HIDDEN
    FULL_ACCESS: object = container.DIR_FULL_ACCESS
    OVERLAY: object = container.DIR_OVERLAY


def run_exec(
    cmd: Sequence[CmdArg] = ("true",),
    cwd: Path = Path().resolve(),
    env: Mapping[CmdArg, CmdArg] = {},
    dir_modes: Mapping[Path, DirMode] = {},
    time_limit: None | int = None,
    mem_limit: None | int = None,
) -> RunexecStats:
    with gen_temp_dir() as tmp_dir:
        stdout = tmp_dir / "stdout"
        stderr = tmp_dir / "stderr"
        dir_modes_processed = {
            **{
                "/": DirMode.READ_ONLY,
                "/home": DirMode.HIDDEN,
                "/run": DirMode.HIDDEN,
                "/tmp": DirMode.HIDDEN,
                "/var": DirMode.HIDDEN,
            },
            **{
                f"{path if path.is_absolute() else path.resolve()}": mode
                for path, mode in dir_modes.items()
            },
        }
        # https://github.com/sosy-lab/benchexec/blob/2c56e08d5f0f44b3073f9c82a6c5f166a12b45e7/benchexec/runexecutor.py#L304
        # https://github.com/sosy-lab/benchexec/blob/2c56e08d5f0f44b3073f9c82a6c5f166a12b45e7/benchexec/containerexecutor.py#L297
        run_executor = RunExecutor(
            use_namespaces=True,
            gid=os.getgid(),
            uid=os.getuid(),
            dir_modes=dir_modes_processed,
            network_access=False,
            container_system_config=True,
            container_tmpfs=True,
        )
        with runexec_catch_signals(run_executor):
            hard_time_limit = (
                int(time_limit * 1.1)
                if time_limit is not None else
                None
            )
            run_exec_run = run_executor.execute_run(
                args=tuple(map(cmd_arg, cmd)),
                environments={
                    "newEnv": {
                        cmd_arg(key): cmd_arg(val)
                        for key, val in env.items()
                    },
                },
                workingDir=cmd_arg(cwd),
                write_header=False,
                output_filename=stdout,
                error_filename=stderr,
                softtimelimit=time_limit,
                hardtimelimit=hard_time_limit,
                memlimit=mem_limit,
            )
        return RunexecStats.create(
            run_exec_run,
            stdout.read_bytes(),
            stderr.read_bytes(),
        )
