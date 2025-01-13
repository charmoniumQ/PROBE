from __future__ import annotations
import datetime
import pathlib
import textwrap
import typing
import resource
import shlex
import dataclasses
import subprocess
import os
import errno


class _ResourcePopen(subprocess.Popen):
    def _try_wait(self, wait_flags):
        try:
            (pid, sts, res) = os.wait4(self.pid, wait_flags)
        except OSError as e:
            if e.errno != errno.ECHILD:
                raise
            pid = self.pid
            sts = 0
        else:
            self.rusage = res
        return (pid, sts)


@dataclasses.dataclass
class FailedProcess(Exception):
    proc: CompletedProcess

    def __str__(self) -> str:
        chdir = ("--chdir", str(self.proc.cwd)) if self.proc.cwd else ()
        env_vars = tuple(f"{shlex.quote(key)}={shlex.quote(val)}" for key, val in self.proc.env.items()) + ("-",) if self.proc.env is not None else ()
        env_bin = ("env",) if chdir or env_vars else ()
        cmd = shlex.join(env_bin + chdir + env_vars + self.proc.cmd)
        return "\n".join([
            f"Process failed with status={self.proc.returncode}",
            "  " + cmd,
            "stdout:",
            textwrap.indent(self.proc.stdout.decode(errors="surrogatescape"), "  "),
            "stderr:",
            textwrap.indent(self.proc.stderr.decode(errors="surrogatescape"), "  "),
        ])


@dataclasses.dataclass
class CompletedProcess:
    returncode: int = 0
    cmd: tuple[str, ...] = ()
    cwd: pathlib.Path | None = None
    env: typing.Mapping[str, str] | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    walltime: datetime.timedelta = datetime.timedelta(seconds=0)
    user_cpu_time: datetime.timedelta = datetime.timedelta(seconds=0)
    system_cpu_time: datetime.timedelta = datetime.timedelta(seconds=0)
    max_memory_usage: int = 0
    n_swaps: int = 0
    n_blocks_read: int = 0
    n_blocks_wrote: int = 0
    n_signals: int = 0
    n_voluntary_context_switches: int = 0
    n_involuntary_context_switches: int = 0

    @property
    def cpu_time(self) -> datetime.timedelta:
        return self.user_cpu_time + self.system_cpu_time

    @property
    def n_context_switches(self) -> int:
        return self.n_voluntary_context_switches + self.n_involuntary_context_switches

    def raise_for_error(self) -> CompletedProcess:
        if self.returncode != 0:
            raise FailedProcess(self)
        return self


def measure_resources(
        cmd: tuple[str, ...],
        env: typing.Mapping[str, str] | None = None,
        cwd: pathlib.Path | None = None,
        timeout: datetime.timedelta | None = None,
) -> CompletedProcess:
    start = datetime.datetime.now()
    with _ResourcePopen(
            cmd,
            env=env,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
    ) as p:
        try:
            stdout, stderr = p.communicate(timeout=timeout.total_seconds() if timeout is not None else None)
            stop = datetime.datetime.now()
        except:
            p.kill()
            stdout, stderr = p.communicate()
            raise
        return CompletedProcess(
            p.returncode,
            cmd,
            cwd,
            env,
            stdout,
            stderr,
            (stop - start),
            datetime.timedelta(seconds=p.rusage.ru_utime),
            datetime.timedelta(seconds=p.rusage.ru_stime),
            p.rusage.ru_maxrss,
            p.rusage.ru_nswap,
            p.rusage.ru_inblock,
            p.rusage.ru_oublock,
            p.rusage.ru_nsignals,
            p.rusage.ru_nvcsw,
            p.rusage.ru_nivcsw,
        )
