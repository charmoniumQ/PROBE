#!/usr/bin/env python
import typer
import enum
from typing_extensions import Annotated
import experiment
import workloads as workloads_mod
import prov_collectors as prov_collectors_mod
import util
import stats
import polars


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
) -> None:
    """
    Run a full matrix of these workloads in those provenance collectors.

    This program writes intermediate results to disk, so if it gets interrupted part
    way through, it can pick back up where it left of last time. However, if you really
    want to ignore prior runs, pass `--rerun`.

    """

    collector_list = list(util.flatten1([
        prov_collectors_mod.PROV_COLLECTOR_GROUPS[collector_name.value]
        for collector_name in collectors
    ]))
    workload_list = list(util.flatten1([
        workloads_mod.WORKLOAD_GROUPS[workload_name.value]
        for workload_name in workloads
    ]))
    if not collectors:
        raise ValueError("Must select some collectors")
    if not workloads:
        raise ValueError("Must select some workloads")

    iterations_df, workloads_df = stats.process_df(experiment.run_experiments(
        collector_list,
        workload_list,
        iterations=iterations,
        seed=seed,
        rerun=rerun,
    ))
    failures = iterations_df.filter(polars.col("returncode") != 0).select(
        "collector",
        "workload_subgroup",
    )
    if not failures.is_empty():
        for failure in failures:
            print("Failures:")
            print(*failure)
    print(iterations_df.select(*[
        col
        for col in iterations_df.columns
        if ("time" in col and "overhead" in col) or "subsubgroup" in col or "collector" in col
    ]))
    iterations_df.write_parquet("iterations.parquet")
    workloads_df.write_parquet("workloads.parquet")


if __name__ == "__main__":
    typer.run(main)
