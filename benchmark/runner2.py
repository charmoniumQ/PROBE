import typer
from typing_extensions import Annotated
from experiment import get_results
from workloads import WORKLOAD_GROUPS
from prov_collectors import PROV_COLLECTORS
from stats3 import STATS
from util import flatten1


def main(
        collector_names: Annotated[list[str], typer.Option("--collectors", "-c")] = ["noprov"],
        workload_names: Annotated[list[str], typer.Option("--workloads", "-w")] = ["gcc"],
        stats_names: Annotated[list[str], typer.Option("--stats", "-s")] = ["performance"],
        iterations: int = 1,
        seed: int = 0,
        rerun: Annotated[bool, typer.Option("--rerun")] = False,
        ignore_failures: Annotated[bool, typer.Option("--keep-going")] = True,
) -> None:
    collectors = [
        PROV_COLLECTORS[collector_name]
        for collector_name in collector_names
    ]
    workloads = list(flatten1([
        WORKLOAD_GROUPS[workload_name]
        for workload_name in workload_names
    ]))
    stats = [
        STATS[stats_name]
        for stats_name in stats_names
    ]
    if not collectors:
        raise ValueError("Must select some collectors")
    if not workloads:
        raise ValueError("Must select some workloads")
    df = get_results(
        collectors,
        workloads,
        iterations=iterations,
        seed=0,
        ignore_failures=ignore_failures,
        rerun=rerun,
    )
    for stat in stats:
        stat(df)


if __name__ == "__main__":
    typer.run(main)
