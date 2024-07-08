import os
import dataclasses
import hashlib
import urllib.parse
import shutil
import subprocess
import sys
import itertools
import json
import random
import pathlib
import collections
import typing
import tqdm  # type: ignore
import pickle
import pandas  # type: ignore
import psutil
import charmonium.time_block as ch_time_block
from collections.abc import Sequence, Mapping
from workloads import Workload
from prov_collectors import ProvCollector, ProvOperation
from run_exec_wrapper import run_exec, DirMode
from util import (
    delete_children, move_children,
    hardlink_children, shuffle, expect_type, to_str, merge_env_vars,
    SubprocessError, get_nix_env,
)


result_bin = pathlib.Path("result").resolve() / "bin"
result_lib = result_bin.parent / "lib"


def get_results(
        prov_collectors: Sequence[ProvCollector],
        workloads: Sequence[Workload],
        iterations: int,
        seed: int,
        ignore_failures: bool,
        rerun: bool,
        parallelism: int,
) -> pandas.DataFrame:
    cache_dir = pathlib.Path(".cache")
    big_temp_dir = pathlib.Path(".workdir")
    size = 256
    key = (cache_dir / ("results_" + "_".join([
        *[prov_collector.name for prov_collector in prov_collectors],
        hashlib.sha256("".join(sorted(workload.name for workload in workloads)).encode()).hexdigest()[:10],
        str(iterations),
        str(size),
        str(seed),
    ]) + ".pkl"))
    # If we are rerunning anything, then we can't trust the aggregated results
    if rerun:
        for file in cache_dir.iterdir():
            if file.name.startswith("results_"):
                file.unlink()
    if key.exists():
        with key.open("rb") as key_file:
            return expect_type(pandas.DataFrame, pickle.load(key_file))
    else:
        results_df = run_experiments(
            prov_collectors,
            workloads,
            cache_dir,
            big_temp_dir,
            iterations,
            size,
            seed,
            ignore_failures,
            rerun,
            parallelism,
        )
        key.write_bytes(pickle.dumps(results_df))
        return results_df


def run_experiments(
        prov_collectors: Sequence[ProvCollector],
        workloads: Sequence[Workload],
        cache_dir: pathlib.Path,
        big_temp_dir: pathlib.Path,
        iterations: int,
        size: int,
        seed: int,
        ignore_failures: bool,
        rerun: bool,
        parallelism: int,
) -> pandas.DataFrame:
    prng = random.Random(seed)
    # Shuffle within each iteration
    # all iteration=0 come before iteration=1, but within each iteration, workloads and prov_collectors are shuffled differently
    inputs = list(itertools.chain.from_iterable(
        shuffle(
            prng,
            tuple(itertools.product([iteration], prov_collectors, workloads)),
        )
        for iteration in range(iterations)
    ))
    big_temp_dir.mkdir(exist_ok=True, parents=True)
    temp_dir = big_temp_dir / "temp"
    log_dir = big_temp_dir / "log"
    artifacts_dir = big_temp_dir / "artifacts"
    work_dir = big_temp_dir / "work"
    temp_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)
    work_dir.mkdir(exist_ok=True)
    assert list(inputs)
    if parallelism == 1:
        result_list = (
            (prov_collector, workload, run_one_experiment_cached(
                cache_dir, iteration, prov_collector, workload,
                work_dir, log_dir, temp_dir, artifacts_dir, size, ignore_failures,
                rerun,
            ))
            for iteration, prov_collector, workload in tqdm.tqdm(inputs)
        )
    else:
        import dask
        import dask.diagnostics
        dask.diagnostics.ProgressBar().register()
        result_list = dask.compute(
            [
                (prov_collector, workload, dask.delayed(run_one_experiment_cached)(
                    cache_dir, iteration, prov_collector, workload,
                    work_dir, log_dir, temp_dir, artifacts_dir, size, ignore_failures,
                    rerun,
                ))
                for iteration, prov_collector, workload in tqdm.tqdm(inputs)
            ],
            scheduler="processes",
            num_workers=parallelism,
        )[0]

    records: list[dict[str, object] | None] = [None] * (len(prov_collectors) * len(workloads) * iterations)
    # Loop through each one at a time
    # Extracting a minimal set of fields
    # So we don't have all ExperimentStats in memory at once
    for i, (prov_collector, workload, stats) in enumerate(result_list):
        counter = collections.Counter(
            op.type for op in stats.operations
        ) if stats is not None else None
        record = {
            "collector": prov_collector.name,
            "collector_method": prov_collector.method,
            "collector_submethod": prov_collector.submethod,
            "workload": workload.name,
            "workload_kind": workload.kind,
            "cputime": stats.cputime,
            "walltime": stats.walltime,
            "memory": stats.memory,
            "storage": stats.provenance_size,
            "n_ops": len(stats.operations),
            # "n_unique_files": n_unique(itertools.chain(
            #     (op.target0 for op in stats.operations),
            #     (op.target1 for op in stats.operations),
            # )),
            "op_type_counts": counter,
        } if stats is not None else None
        records.append(record)
    results_df = (
        pandas.DataFrame.from_records(list(filter(bool, records)))
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
    operations: tuple[ProvOperation, ...]


def run_one_experiment_cached(
    cache_dir: pathlib.Path,
    iteration: int,
    prov_collector: ProvCollector,
    workload: Workload,
    work_dir: pathlib.Path,
    log_dir: pathlib.Path,
    temp_dir: pathlib.Path,
    artifacts_dir: pathlib.Path,
    size: int,
    ignore_failures: bool,
    rerun: bool,
) -> ExperimentStats | None:
    key = (cache_dir / ("_".join([
        urllib.parse.quote(prov_collector.name, safe=''),
        urllib.parse.quote(workload.name, safe=''),
        str(iteration)
    ]))).with_suffix(".pkl")
    if (not rerun) and key.exists():
        with ch_time_block.ctx(f"pickle.loads {prov_collector.name} {workload.name} {iteration}", do_gc=True):
            with key.open("rb") as key_file:
                return expect_type(ExperimentStats, pickle.load(key_file))
    else:
        delete_children(temp_dir)
        stats = run_one_experiment(
            iteration, prov_collector, workload, work_dir, log_dir,
            temp_dir, artifacts_dir, size, ignore_failures,
        )
        if stats is not None:
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
    artifacts_dir: pathlib.Path,
    size: int,
    ignore_failures: bool,
) -> ExperimentStats | None:
    # This even works when we don't have parallelism:
    this_process = psutil.Process()
    parent_process = this_process.parent()
    sibling_processes = parent_process.children()
    worker_number = sibling_processes.index(this_process)

    # This renames the relevant directories so they don't conflict with other workers
    work_dir = work_dir / str(worker_number)
    log_dir = log_dir / str(worker_number)
    temp_dir = temp_dir / str(worker_number)

    workload_name = "-".join([workload.superkind, workload.kind, workload.name]).lower()

    with ch_time_block.ctx(f"Compiling Nix env for {prov_collector} and {workload_name}"):
        collector_env = get_nix_env(prov_collector.nix_packages)
        workload_env = get_nix_env(workload.nix_packages)

    with ch_time_block.ctx(f"setup {workload_name}"):
        try:
            work_dir.mkdir(exist_ok=True, parents=True)
            workload.setup(work_dir, workload_env)
        except SubprocessError as exc:
            print(str(exc))
            return ExperimentStats(
                cputime=0,
                walltime=0,
                memory=0,
                provenance_size=0,
                operations=(),
            )
        log_dir.mkdir(exist_ok=True, parents=True)
        delete_children(log_dir)

    with ch_time_block.ctx(f"setup {prov_collector}"):
        if prov_collector.requires_empty_dir:
            (temp_dir / "old_work_dir").mkdir()
            hardlink_children(work_dir, temp_dir / "old_work_dir")
            delete_children(work_dir)
            prov_collector.start(log_dir, size, work_dir, collector_env)
            move_children(temp_dir / "old_work_dir", work_dir)
        else:
            prov_collector.start(log_dir, size, work_dir, collector_env)
        cmd = workload.run(work_dir)
        # TODO: factor out custom_env
        prog = cmd[0]
        if isinstance(prog, pathlib.Path):
            main_executable = prog
        elif isinstance(prog, str):
            _main_executable = shutil.which(str(prog), path=workload_env["PATH"])
            if _main_executable is None:
                raise RuntimeError(f"{prog} not found in {workload_env['PATH']}")
            main_executable = pathlib.Path(_main_executable)
        cmd = prov_collector.run(cmd, log_dir, size)
        # cmd = (result_bin / "setarch", "--addr-no-randomize", *cmd)


    with ch_time_block.ctx(f"run {workload_name} in {prov_collector}"):
        full_env = merge_env_vars(workload_env, collector_env)
        print(cmd, full_env)
        stats = run_exec(
            cmd=cmd,
            env=full_env,
            dir_modes={
                work_dir: DirMode.FULL_ACCESS,
                log_dir: DirMode.FULL_ACCESS,
                pathlib.Path(): DirMode.READ_ONLY,
                pathlib.Path("/nix/store"): DirMode.READ_ONLY,
            },
            network_access=workload.network_access,
        )

    prov_collector.stop(collector_env)

    if not stats.success:
        if ignore_failures:
            return None
        else:
            raise SubprocessError(
                cmd=cmd,
                env=full_env,
                cwd=None,
                returncode=stats.exitcode,
                stdout=to_str(stats.stdout),
                stderr=to_str(stats.stderr),
            )
    with ch_time_block.ctx(f"parse {prov_collector}"):
        provenance_size = 0
        for child in log_dir.iterdir():
            provenance_size += child.stat().st_size
        operations = prov_collector.count(log_dir, main_executable)
        # artifact_dir = artifacts_dir / ("_".join([
        #     urllib.parse.quote(prov_collector.name),
        #     workload.name,
        #     str(iteration)
        # ]))
        # if artifact_dir.exists():
        #     shutil.rmtree(artifact_dir)
        # artifact_dir.mkdir(parents=True)
        # move_children(log_dir, artifact_dir)
    sys.stdout.buffer.write(stats.stdout)
    sys.stderr.buffer.write(stats.stderr)
    return ExperimentStats(
        cputime=stats.cputime,
        walltime=stats.walltime,
        memory=stats.memory,
        provenance_size=provenance_size,
        operations=operations,
    )
