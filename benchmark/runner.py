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
) -> None:
    """
    Run a full matrix of these workloads in those provenance collectors.

    This program writes intermediate results to disk, so if it gets interrupted part
    way through, it can pick back up where it left of last time. However, if you really
    want to ignore prior runs, pass `--rerun`.

    """
    entry = datetime.datetime.now()
    if verbose:
        util.console.print(f"Finished imports in {(imports - start).total_seconds():.1f}sec")
        util.console.print(f"Entered main in {(entry - imports).total_seconds():.1f}sec")

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

    storage_file = pathlib.Path(".cache/run_experiments.db")
    storage_file.parent.mkdir(exist_ok=True)
    collectors_str = ", ".join(collector.name for collector in collector_list)
    workloads_str = ", ".join(workload.labels[0][-1] for workload in workload_list)
    prompt = " ".join([
        "This operation will DELETE previous:",
        f"{collectors_str} x {workloads_str} x {iterations} ({seed=}).",
        "Continue?",
    ])
    if rerun and rich.prompt.Confirm.ask(prompt, console=util.console):
        ops = []
        util.console.print("Dropping calls")
        with Storage(storage_file) as storage:
            # ops.append(experiment.run_experiments(
            #     collector_list,
            #     workload_list,
            #     iterations=iterations,
            #     seed=seed,
            #     rerun=rerun,
            #     verbose=Ignore(verbose),
            # ))
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
        storage.cleanup_refs()
        util.console.print("Done dropping calls")
    with Storage(storage_file) as storage:
        # iterations_df = storage.unwrap(experiment.run_experiments(
        #     collector_list,
        #     workload_list,
        #     iterations=iterations,
        #     seed=seed,
        #     rerun=rerun,
        #     verbose=Ignore(verbose),
        # ))
        iterations_df = experiment.run_experiments(
            collector_list,
            workload_list,
            iterations=iterations,
            seed=seed,
            rerun=rerun,
            verbose=verbose,
        )

    stats.process_df(iterations_df)

    if verbose:
        util.console.print(f"Finished main in {(datetime.datetime.now() - entry).total_seconds():.1f}sec")


if __name__ == "__main__":
    with util.progress:
        typer.run(main)
