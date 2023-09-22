import numpy
import dataclasses
import hashlib
import warnings
import urllib.parse
import shlex
import itertools
import random
import pathlib
import charmonium.time_block as ch_time_block
import tqdm  # type: ignore
import pickle
import collections
import pandas
from collections.abc import Sequence
from workloads import WORKLOADS, Workload
from prov_collectors import PROV_COLLECTORS, ProvCollector, baseline
from run_exec_wrapper import RunexecStats, run_exec, DirMode
from util import gen_temp_dir, delete_children, move_children, shuffle, expect_type, groupby_dict, first, confidence_interval


def print_results(
        prov_collectors: Sequence[ProvCollector] = PROV_COLLECTORS[:2],
        workloads: Sequence[Workload] = WORKLOADS[:2],
        iterations: int = 2,
        seed: int = 0,
        confidence_level: float = 0.94
) -> str:
    df = aggregate_results(prov_collectors, workloads, iterations, seed, confidence_level)
    print(df[[
        ("cputime", "rel_mid"),
        ("walltime", "rel_mid"),
        ("memory", "rel_mid"),
        ("storage", "abs_mid"),
        ("n_files", "abs_mid"),
    ]])


def aggregate_results(
        prov_collectors: Sequence[ProvCollector] = PROV_COLLECTORS[:2],
        workloads: Sequence[Workload] = WORKLOADS[:2],
        iterations: int = 2,
        seed: int = 0,
        confidence_level: float = 0.94
) -> pandas.DataFrame:
    rel_qois = ["cputime", "walltime", "memory"]
    abs_qois = ["n_files", "storage"]
    return (
        run_experiments_cached(
            prov_collectors,
            workloads,
            iterations=iterations,
            seed=seed,
            cache_dir=pathlib.Path(".cache"),
            big_temp_dir=pathlib.Path(".workdir"),
            size=256,
        )
        .assign(lambda df: {
            "n_files": map(len, df["files"])
        })
        .groupby(("collector", "workload"), as_index=True)
        .apply(lambda df: {
            **{
                (qoi, "abs_low"): confidence_interval(df[qoi].values, confdience_level, seed=seed)[0]
                for qoi in rel_qois + abs_qois
            },
            **{
                (qoi, "abs_high"): confidence_interval(df[qoi].values, confdience_level, seed=seed)[1]
                for qoi in rel_qois + abs_qois
            },
        })
        .assign(lambda df: {
            **{
                (qoi, "rel_low"): [
                    df[(collector, workload), (qoi, "abs_low")] / df[(baseline, workload), (qoi, "abs_high")]
                    for collector, workload in df.index
                ]
                for qoi in rel_qois
            },
            **{
                (qoi, "rel_high"): [
                    df[(collector, workload), (qoi, "abs_high")] / df[(baseline, workload), (qoi, "abs_low")]
                    for collector, workload in df.index
                ]
                for qoi in rel_qois
            },
        })
        .assign(lambda df: {
            **{
                (qoi, f"{prefix}_mid"): (df.loc[(qoi, f"{prefix}_high")] + df.loc[(qoi, f"{prefix}_low")]) / 2
                for qoi, prefix in [(qoi, "rel") for qoi in rel_qois] + [(qoi, "abs") for qoi in abs_qois]
            },
            **{
                (qoi, f"{prefix}_err"): (df.loc[(qoi, f"{prefix}_high")] - df.loc[(qoi, f"{prefix}_low")]) / 2
                for qoi, prefix in [(qoi, "rel") for qoi in rel_qois] + [(qoi, "abs") for qoi in abs_qois]
            },
        })
    )


def run_experiments_cached(
        prov_collectors: Sequence[ProvCollector],
        workloads: Sequence[Workload],
        iterations: int,
        seed: int,
        cache_dir: pathlib.Path = pathlib.Path(".cache"),
        big_temp_dir: pathlib.Path = pathlib.Path(".workdir"),
        size: int = 256,
) -> pandas.DataFrame:
    key = (cache_dir / ("results_" + "_".join([
        *[prov_collector.name for prov_collector in prov_collectors],
        *[workload.name for workload in workloads],
        str(iterations),
        str(size),
        str(seed),
    ]) + ".pkl"))
    if key.exists():
        return expect_type(pandas.DataFrame, pickle.loads(key.read_bytes()))
    else:
        results_df = run_experiments(
            prov_collectors,
            workloads,
            cache_dir,
            big_temp_dir,
            iterations,
            size,
            seed,
        )
        key.write_bytes(pickle.dumps(results_df))
        return results_df


def run_experiments(
        prov_collectors: Sequence[ProvCollector],
        workloads: Sequence[Workload],
        cache_dir: pathlib.Path,
        big_temp_dir: pathlib.Path,
        iterations: int = 10,
        size: int = 256,
        seed: int = 0,
) -> None:
    prng = random.Random(seed)
    inputs = shuffle(
        prng,
        tuple(itertools.product(range(iterations), prov_collectors, workloads)),
    )
    big_temp_dir.mkdir(exist_ok=True, parents=True)
    temp_dir = big_temp_dir / "temp"
    log_dir = big_temp_dir / "log"
    work_dir = big_temp_dir / "work"
    result_list = [
        (prov_collector, workload, run_one_experiment_cached(
            cache_dir, iteration, prov_collector, workload,
            work_dir, log_dir, temp_dir, size,
        ))
        for iteration, prov_collector, workload in tqdm.tqdm(inputs)
    ]
    results_df = (
        pandas.DataFrame.from_records(
            {
                "collector": prov_collector.name,
                "collector_method": prov_collector.method,
                "collector_submethod": prov_collector.submethod,
                "workload": workload.name,
                "workload_type": workload.type,
                "cputime": stats.cputime,
                "walltime": stats.walltime,
                "memory": stats.memory,
                "storage": stats.provenance_size,
                "files": stats.files,
                "call_counts": stats.call_counts,
            }
            for prov_collector, workload, stats in result_list
        )
        .assign(lambda df: {
            "collector": df["collector"].astype("category"),
            "collector_method": df["collector_method"].astype("category"),
            "collector_submethod": df["collector_submethod"].astype("category"),
            "workload": df["workload"].astype("category"),
            "workload_type": df["workload_type"].astype("category"),
        })
    )
    return results_df


@dataclasses.dataclass
class ExperimentStats:
    cputime: int
    walltime: int
    memory: int
    provenance_size: int
    files: frozenset[str]
    call_counts: collections.Counter[str]


def run_one_experiment_cached(
    cache_dir: pathlib.Path,
    iteration: int,
    prov_collector: ProvCollector,
    workload: Workload,
    work_dir: pathlib.Path,
    log_dir: pathlib.Path,
    temp_dir: pathlib.Path,
    size: int,
) -> ExperimentStats:
    key = (cache_dir / ("_".join([
        urllib.parse.quote(prov_collector.name),
        workload.name,
        str(iteration)
    ]))).with_suffix(".pkl")
    if key.exists():
        return expect_type(RunexecStats, pickle.loads(key.read_bytes()))
    else:
        stats = run_one_experiment(
            iteration, prov_collector, workload, work_dir, log_dir,
            temp_dir, size
        )
        cache_dir.mkdir(exist_ok=True, parents=True)
        key.write_bytes(pickle.dumps(stats))
        return stats


def run_one_experiment(
    iteration: int,
    prov_collector: ProvCollector,
    workload: Workload,
    work_dir: pathlib.Path,
    log_dir: pathlib.Path,
    temp_dir: pathlib.Path,
    size: int,
) -> ExperimentStats:

    log_dir.mkdir(exist_ok=True, parents=True)
    log_path = log_dir / "logs"

    with ch_time_block.ctx(f"setup {workload}"):
        workload.setup(work_dir)
        delete_children(log_dir)

    with ch_time_block.ctx(f"setup {prov_collector}"):
        if prov_collector.requires_empty_dir:
            delete_children(temp_dir)
            move_children(work_dir, temp_dir)
            prov_collector.start(log_path, size, work_dir)
            move_children(temp_dir, work_dir)
        else:
            prov_collector.start(log_path, size, work_dir)
        cmd = prov_collector.run(workload.run(work_dir), log_path, size)

    with ch_time_block.ctx(f"{workload} in {prov_collector}"):
        stats = run_exec(
            cmd=cmd,
            dir_modes={
                work_dir: DirMode.OVERLAY,
                log_dir: DirMode.FULL_ACCESS,
                pathlib.Path().resolve(): DirMode.READ_ONLY,
            },
        )
        print(stats.stdout.decode(errors="replace"))
        print(stats.stderr.decode(errors="replace"))
    if not stats.success:
        warnings.warn(
            "\n".join([
                f"{prov_collector} on {workload} failed",
                shlex.join(map(str, cmd)),
                "stdout:",
                stats.stdout.decode(errors="replace"),
                "stderr:",
                stats.stderr.decode(errors="replace"),
            ])
        )
    provenance_size = 0
    for child in log_dir.iterdir():
        provenance_size += log_path.stat().st_size
    call_counts, files = prov_collector.count(log_path)
    return ExperimentStats(
        cputime=stats.cputime,
        walltime=stats.walltime,
        memory=stats.memory,
        provenance_size=provenance_size,
        files=files,
        call_counts=call_counts,
    )


if __name__ == "__main__":
    print(aggregate_results())
