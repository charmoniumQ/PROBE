import typer
import pathlib
import datetime
from typing_extensions import Annotated
from experiment import get_results
from workloads import WORKLOAD_GROUPS
from prov_collectors import PROV_COLLECTOR_GROUPS
from stats import STATS
from util import flatten1
import enum


CollectorGroup = enum.Enum("CollectorGroup", {key: key for key in PROV_COLLECTOR_GROUPS})  # type: ignore
WorkloadGroup = enum.Enum("WorkloadGroup", {key: key for key in WORKLOAD_GROUPS.keys()})  # type: ignore
StatsNames = enum.Enum("Sats", {key: key for key in STATS.keys()})  # type: ignore


def main(
        collector_groups: Annotated[list[CollectorGroup], typer.Option("--collectors", "-c")] = [CollectorGroup.noprov],
        workload_groups: Annotated[list[WorkloadGroup], typer.Option("--workloads", "-w")] = [WorkloadGroup["hello"]],
        stats_names: Annotated[list[StatsNames], typer.Option("--stats", "-s")] = [],
        iterations: int = 1,
        seed: int = 0,
        rerun: Annotated[bool, typer.Option("--rerun")] = False,
        ignore_failures: Annotated[bool, typer.Option("--keep-going")] = False,
        parallelism: int = 1,
) -> None:
    collectors = list(flatten1([
        PROV_COLLECTOR_GROUPS[collector_name.value]
        for collector_name in collector_groups
    ]))
    workloads = list(flatten1([
        WORKLOAD_GROUPS[workload_name.value]
        for workload_name in workload_groups
    ]))
    stats = [
        STATS[stats_name.value]
        for stats_name in stats_names
    ]
    if not collectors:
        raise ValueError("Must select some collectors")
    if not workloads:
        raise ValueError("Must select some workloads")
    with pathlib.Path("runner.log").open("a+") as file:
        print("Starting", datetime.datetime.now().isoformat(), file=file)
        print(", ".join(collector_group.value for collector_group in collector_groups), file=file)
        print(", ".join(workload_group.value for workload_group in workload_groups), file=file)
    df = get_results(
        collectors,
        workloads,
        iterations=iterations,
        seed=0,
        ignore_failures=ignore_failures,
        rerun=rerun,
        parallelism=parallelism,
    )
    with pathlib.Path("runner.log").open("a+") as file:
        print("Done", datetime.datetime.now().isoformat(), file=file)
    for stat in stats:
        stat(df)


if __name__ == "__main__":
    typer.run(main)
