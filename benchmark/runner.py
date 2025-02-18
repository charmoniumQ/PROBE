#!/usr/bin/env python
import datetime; start = datetime.datetime.now()
import typer
import pathlib
import enum
from typing_extensions import Annotated
import experiment
import workloads as workloads_mod
import prov_collectors as prov_collectors_mod
import rich.prompt
import util
from pympler.asizeof import asizeof as size
import stats
from mandala.imports import Storage, Ignore

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
        seed: int = 0,
        rerun: Annotated[bool, typer.Option("--rerun")] = False,
        verbose: Annotated[bool, typer.Option("--verbose")] = False,
        storage_file: pathlib.Path = pathlib.Path(".cache/run_experiments.db"),
) -> None:
    """
    Run a full matrix of these workloads in those provenance collectors.

    This program writes intermediate results to disk, so if it gets interrupted part
    way through, it can pick back up where it left of last time. However, if you really
    want to ignore prior runs, pass `--rerun`.

    """
    if verbose:
        util.console.print(f"Finished imports in {(imports - start).total_seconds():.1f}sec")

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

    collectors_str = [collector.name for collector in collector_list]
    workloads_str = [workload.labels[0][-1] for workload in workload_list]
    prompt = " ".join([
        "This operation will DELETE previous:",
        f"{collectors_str} x {workloads_str} x {list(range(iterations))} ({seed=}).",
        "Continue?\n",
    ])
    storage_file.parent.mkdir(exist_ok=True)
    if rerun and rich.prompt.Confirm.ask(prompt, console=util.console):
        ops = []
        util.console.print("Dropping calls")
        with Storage(storage_file) as storage:
            ops.extend([
                experiment.run_experiment(seed ^ iteration, collector, workload, Ignore(False))
                for collector in collector_list
                for workload in workload_list
                for iteration in range(iterations)
            ])
        storage.drop_calls(
            [storage.get_ref_creator(op) for op in ops],
            delete_dependents=True,
        )
        util.console.print("Done dropping calls")

    iterations_df = experiment.run_experiments(
        collector_list,
        workload_list,
        iterations=iterations,
        seed=seed,
        rerun=rerun,
        verbose=verbose,
        storage_file=storage_file,
    )
    storage = Storage(storage_file)
    if verbose:
        util.console.print(f"Storage: {util.fmt_bytes(size(storage))}")

    if verbose:
        mid = datetime.datetime.now()
        util.console.print(f"Ran experiment in {(mid - start).total_seconds():.1f}sec")

    stats.process_df(iterations_df)
    if verbose:
        print("cleanup")
    storage.cleanup_refs()
    if verbose:
        print("vacuum")
    storage.vacuum()

    if verbose:
        end = datetime.datetime.now()
        util.console.print(f"Wrapepd up experiment in in {(end - mid).total_seconds():.1f}sec")


if __name__ == "__main__":
    with util.progress:
        typer.run(main)
