import numpy
import dataclasses
import hashlib
import warnings
import urllib.parse
import shlex
import shutil
import itertools
import random
import pathlib
import charmonium.time_block as ch_time_block
import tqdm  # type: ignore
import pickle
import collections
import pandas  # type: ignore
from collections.abc import Sequence
from workloads import WORKLOADS, Workload
from prov_collectors import PROV_COLLECTORS, ProvCollector, baseline
from run_exec_wrapper import RunexecStats, run_exec, DirMode
from util import (
    gen_temp_dir, delete_children, move_children,
    hardlink_children, shuffle, expect_type, groupby_dict, first,
    confidence_interval, to_str, env_command, cmd_arg, merge_env_vars,
    SubprocessError
)


result_bin = pathlib.Path("result").resolve() / "bin"
result_lib = result_bin.parent / "lib"


def aggregate_results(
        prov_collectors: Sequence[ProvCollector] = PROV_COLLECTORS,
        workloads: Sequence[Workload] = WORKLOADS[:3],
        iterations: int = 1,
        seed: int = 0,
        confidence_level: float = 0.94
) -> pandas.DataFrame:
    rel_qois = ["cputime", "walltime", "memory"]
    abs_qois = ["storage", "n_files"]
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
        .assign(**{
            "n_files": lambda df: list(map(len, df["files"]))
        })
        .groupby(["workload", "collector"], as_index=True)
        .agg(**{
            **{
                qoi + "_abs_mean": pandas.NamedAgg(
                    column=qoi,
                    aggfunc=numpy.mean,
                )
                for qoi in rel_qois + abs_qois
            },
            # **{
            #     qoi + "_abs_low": pandas.NamedAgg(
            #         column=qoi,
            #         aggfunc=lambda series: confidence_interval(series.values, confidence_level, seed=seed)[0],
            #     )
            #     for qoi in rel_qois + abs_qois
            # },
            # **{
            #     qoi + "_abs_high": pandas.NamedAgg(
            #         column=qoi,
            #         aggfunc=lambda series: confidence_interval(series.values, confidence_level, seed=seed)[1],
            #     )
            #     for qoi in rel_qois + abs_qois
            # },
        })
        # .assign(**{
        #     **{
        #         (qoi, "rel_low"): lambda df: [
        #             df[(collector, workload), (qoi, "abs_low")] / df[(baseline, workload), (qoi, "abs_high")]
        #             for collector, workload in df.index
        #         ]
        #         for qoi in rel_qois
        #     },
        #     **{
        #         (qoi, "rel_high"): lambda df: [
        #             df[(collector, workload), (qoi, "abs_high")] / df[(baseline, workload), (qoi, "abs_low")]
        #             for collector, workload in df.index
        #         ]
        #         for qoi in rel_qois
        #     },
        # })
        # .assign(**{
        #     **{
        #         (qoi, f"{prefix}_mid"): lambda df: (df.loc[(qoi, f"{prefix}_high")] + df.loc[(qoi, f"{prefix}_low")]) / 2
        #         for qoi, prefix in [(qoi, "rel") for qoi in rel_qois] + [(qoi, "abs") for qoi in abs_qois]
        #     },
        #     **{
        #         (qoi, f"{prefix}_err"): lambda df: (df.loc[(qoi, f"{prefix}_high")] - df.loc[(qoi, f"{prefix}_low")]) / 2
        #         for qoi, prefix in [(qoi, "rel") for qoi in rel_qois] + [(qoi, "abs") for qoi in abs_qois]
        #     },
        # })
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
) -> pandas.DataFrame:
    prng = random.Random(seed)
    inputs = shuffle(
        prng,
        tuple(itertools.product(range(iterations), prov_collectors, workloads)),
    )
    big_temp_dir.mkdir(exist_ok=True, parents=True)
    temp_dir = big_temp_dir / "temp"
    log_dir = big_temp_dir / "log"
    work_dir = big_temp_dir / "work"
    temp_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)
    work_dir.mkdir(exist_ok=True)
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
                "workload_kind": workload.kind,
                "cputime": stats.cputime,
                "walltime": stats.walltime,
                "memory": stats.memory,
                "storage": stats.provenance_size,
                "files": stats.files,
                "call_counts": stats.call_counts,
            }
            for prov_collector, workload, stats in result_list
        )
        .assign(**{
            "collector": lambda df: df["collector"].astype("category"),
            "collector_method": lambda df: df["collector_method"].astype("category"),
            "collector_submethod": lambda df: df["collector_submethod"].astype("category"),
            "workload": lambda df: df["workload"].astype("category"),
            "workload_kind": lambda df: df["workload_kind"].astype("category"),
        })
    )
    return results_df


@dataclasses.dataclass
class ExperimentStats:
    cputime: float
    walltime: float
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
        return expect_type(ExperimentStats, pickle.loads(key.read_bytes()))
    else:
        delete_children(temp_dir)
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
    log_path = log_dir / "logs"

    with ch_time_block.ctx(f"setup {workload}"):
        workload.setup(work_dir)
        delete_children(log_dir)

    (temp_dir / "old_work_dir").mkdir()
    hardlink_children(work_dir, temp_dir / "old_work_dir")
    # We will restore temp_dir to this state after running the experiment

    with ch_time_block.ctx(f"setup {prov_collector}"):
        if prov_collector.requires_empty_dir:
            delete_children(work_dir)
            prov_collector.start(log_path, size, work_dir)
            move_children(temp_dir / "old_work_dir", work_dir)
        else:
            prov_collector.start(log_path, size, work_dir)
        cmd, env = workload.run(work_dir)
        cmd = prov_collector.run(cmd, log_path, size)

    with ch_time_block.ctx(f"{workload} in {prov_collector}"):
        full_env = merge_env_vars(
            env,
            {
                "LD_LIBRARY_PATH": str(result_lib),
                "LIBRARY_PATH": str(result_lib),
                "PATH": str(result_bin),
            },
        )
        stats = run_exec(
            cmd=cmd,
            env=full_env,
            dir_modes={
                work_dir: DirMode.FULL_ACCESS,
                log_dir: DirMode.FULL_ACCESS,
            },
        )
    move_children(temp_dir / "old_work_dir", work_dir)
    if not stats.success:
        raise SubprocessError(
            cmd=cmd,
            env=full_env,
            cwd=None,
            returncode=stats.exitcode,
            stdout=to_str(stats.stdout),
            stderr=to_str(stats.stderr),
        )
    provenance_size = 0
    for child in log_dir.iterdir():
        provenance_size += child.stat().st_size
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
