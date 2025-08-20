#!/usr/bin/env python
from __future__ import annotations
# ruff: noqa: E402
import datetime
start = datetime.datetime.now()
import dataclasses
import pathlib
import subprocess
import typer
import json
import polars
import enum
from typing_extensions import Annotated
import experiment
import workloads as workloads_mod
import prov_collectors as prov_collectors_mod
import rich.prompt
import util
from mandala.imports import Storage  # type: ignore
import command

imports = datetime.datetime.now()


CollectorGroup = enum.Enum(  # type: ignore
    "CollectorGroup",
    {key: key for key in prov_collectors_mod.PROV_COLLECTOR_GROUPS if key},
)
WorkloadGroup = enum.Enum(  # type: ignore
    "WorkloadGroup",
    {key: key for key in workloads_mod.WORKLOAD_GROUPS.keys() if key},
)


def main(
        collectors: list[CollectorGroup] = [
            "all"  # type: ignore
        ],
        workloads: list[WorkloadGroup] = [
            "all"  # type: ignore
        ],
        iterations: int = 1,
        warmups: int = 1,
        seed: int = 0,
        rerun: Annotated[bool, typer.Option("--rerun")] = False,
        quiet: Annotated[bool, typer.Option("--quiet")] = False,
        parquet_output: pathlib.Path = pathlib.Path("output/iterations.parquet"),
        internal_cache: pathlib.Path = pathlib.Path(".cache/run_experiments.db"),
        machine_info: pathlib.Path = pathlib.Path("output/machine_info.json"),
        append: bool = False,
) -> None:
    """
    Run a full matrix of these workloads in those provenance collectors.

    This program writes intermediate results to disk, so if it gets interrupted part
    way through, it can pick back up where it left of last time. However, if you really
    want to ignore prior runs, pass `--rerun`.

    """
    # Typer does rich.traceback.install
    # Undo it here
    import sys
    sys.excepthook = sys.__excepthook__

    verbose = not quiet

    if verbose:
        util.console.print(f"Finished imports in {(imports - start).total_seconds():.1f}sec")

    internal_cache.parent.mkdir(exist_ok=True)
    with Storage(internal_cache) as storage:
        minfo = MachineInfo.create()
        machine_info.parent.mkdir(exist_ok=True)
        machine_info.write_text(json.dumps({
            str(minfo.machine_id): dataclasses.asdict(minfo)
        }))

    if verbose:
        util.console.print(f"Machine ID = {minfo.machine_id:08x}")

    collector_list = list(util.flatten1([
        prov_collectors_mod.PROV_COLLECTOR_GROUPS[collector_name.value]
        for collector_name in collectors
    ]))
    workload_list = list(util.flatten1([
        workloads_mod.WORKLOAD_GROUPS[workload_name.value]
        for workload_name in workloads
    ]))
    if not collector_list:
        raise ValueError("Must select some collectors")
    if not workload_list:
        raise ValueError("Must select some workloads")

    parquet_output.parent.mkdir(exist_ok=True)

    collectors_str = [collector.name for collector in collector_list]
    workloads_str = [workload.labels[0][-1] for workload in workload_list]
    prompt = " ".join([
        "This operation will DELETE previous:",
        f"{collectors_str} x {workloads_str} x {list(range(iterations))} ({seed=}).",
        "Continue?\n",
    ])
    internal_cache.parent.mkdir(exist_ok=True)
    parquet_output.parent.mkdir(exist_ok=True)
    if rerun and rich.prompt.Confirm.ask(prompt, console=util.console):
        util.console.print("Dropping calls")
        experiment.drop_calls(
            internal_cache,
            seed,
            iterations,
            collector_list,
            workload_list,
            warmups,
            minfo.machine_id,
        )
        util.console.print("Done dropping calls")

    if append:
        orig_df = polars.read_parquet(parquet_output)
    else:
        orig_df = None

    exp_start = datetime.datetime.now()

    experiment.run_experiments(
        collector_list,
        workload_list,
        iterations=iterations,
        seed=seed,
        verbose=verbose,
        internal_cache=internal_cache,
        parquet_output=parquet_output,
        total_warmups=warmups,
        machine_id=minfo.machine_id,
        orig_df=orig_df,
    )
    storage = Storage(internal_cache)

    if verbose:
        mid = datetime.datetime.now()
        util.console.print(f"Ran experiment in {(mid - exp_start).total_seconds():.1f}sec")

    storage.cleanup_refs()
    storage.vacuum()

    if verbose:
        end = datetime.datetime.now()
        util.console.print(f"Wrapped up experiment in in {(end - mid).total_seconds():.1f}sec")


@dataclasses.dataclass
class MachineInfo:
    machine_id: int
    lshw: str
    uname: str

    @staticmethod
    def create() -> MachineInfo:
        return MachineInfo(
            int(pathlib.Path("/etc/machine-id").read_text(), base=16) & (1 << 32 - 1),
            subprocess.run(
                [command.nix_build(".#lshw") + "/bin/lshw"],
                capture_output=True,
                check=True,
            ).stdout.decode(errors="surrogatescape"),
            subprocess.run(
                [command.nix_build(".#coreutils") + "/bin/uname"],
                capture_output=True,
                check=True,
            ).stdout.decode(errors="surrogatescape"),
        )


if __name__ == "__main__":
    with util.progress:
        typer.run(main)
