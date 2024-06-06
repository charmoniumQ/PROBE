import io
import os
import tempfile
import subprocess
import typing_extensions
import tarfile
import pathlib
import typer
import shutil
from . import parse_probe_log
from . import util


project_root = pathlib.Path(__file__).resolve().parent.parent


A = typing_extensions.Annotated


app = typer.Typer()


@app.command()
def record(
        cmd: list[str],
        gdb: A[bool, typer.Option(False, help="Run in GDB")] = False,
        debug: A[bool, typer.Option(False, help="Run verbose & debug build of libprobe")] = False,
        make: A[bool, typer.Option(False, help="Run make prior to executing")] = False,
        output: pathlib.Path = pathlib.Path("probe_log"),
):
    """
    Execute CMD... and record its provenance into OUTPUT.
    """
    if make:
        proc = subprocess.run(
            ["make", "--directory", str(project_root / "libprobe"), "all"],
        )
        if proc.returncode != 0:
            typer.secho("Make failed", fg=typer.colors.RED)
            raise typer.Abort()
    if output.exists():
        output.unlink()
    libprobe = project_root / "libprobe/build" / ("libprobe-dbg.so" if debug or gdb else "libprobe.so")
    if not libprobe.exists():
        typer.secho(f"Libprobe not found at {libprobe}", fg=typer.colors.RED)
        raise typer.Abort()
    ld_preload = str(libprobe) + (":" + os.environ["LD_PRELOAD"] if "LD_PRELOAD" in os.environ else "")
    probe_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"probe_log_{os.getpid()}"))
    if gdb:
        subprocess.run(
            ["gdb", "--args", "env", f"PROBE_DIR={probe_dir}", f"LD_PRELOAD={ld_preload}", *cmd],
        )
    else:
        if debug:
            typer.secho(f"Running {cmd} with libprobe into {probe_dir}", fg=typer.colors.GREEN)
        proc = subprocess.run(
            cmd,
            env={**os.environ, "LD_PRELOAD": ld_preload, "PROBE_DIR": str(probe_dir)},
        )
        probe_log_tar_obj = tarfile.open(name=str(output), mode="x:gz")
        probe_log_tar_obj.add(probe_dir, arcname="")
        probe_log_tar_obj.addfile(
            util.default_tarinfo("README"),
            fileobj=io.BytesIO(b"This archive was generated by PROBE."),
        )
        probe_log_tar_obj.close()
        if debug:
            print("PROBE log files:")
            for path in probe_dir.iterdir():
                print(path, os.stat(path).st_size)
        shutil.rmtree(probe_dir)
        raise typer.Exit(proc.returncode)


@app.command()
def process_graph(probe_log: pathlib.Path):
    """
    Write a process graph from PROBE_LOG in DOT/graphviz format.
    """
    if not probe_log.exists():
        typer.secho(f"PROBE_LOG {probe_log} does not exist\nUse `PROBE record --output {probe_log} CMD...` to rectify", fg=typer.colors.RED)
        raise typer.Abort()
    probe_log_tar_obj = tarfile.open(probe_log, "r")
    processes = parse_probe_log.parse_probe_log_tar(probe_log_tar_obj)

    probe_log_tar_obj.close()


@app.command()
def dump(probe_log: pathlib.Path):
    """
    Write the data from PROBE_LOG in a human-readable manner.
    """
    if not probe_log.exists():
        typer.secho(f"PROBE_LOG {probe_log} does not exist\nUse `PROBE record --output {probe_log} CMD...` to rectify", fg=typer.colors.RED)
        raise typer.Abort()
    probe_log_tar_obj = tarfile.open(probe_log, "r")
    for process in parse_probe_log.parse_probe_log_tar(probe_log_tar_obj).processes.values():
        for exec_epoch in process.exec_epochs.values():
            for thread in exec_epoch.threads.values():
                for op in thread.ops:
                    print(op.data)
                print()
    probe_log_tar_obj.close()

app()
