import dataclasses
import hashlib
import urllib.parse
import sys
import itertools
import random
import pathlib
import tqdm  # type: ignore
import pickle
import pandas  # type: ignore
import charmonium.time_block as ch_time_block
from collections.abc import Sequence
from workloads import Workload
from prov_collectors import ProvCollector, ProvOperation
from run_exec_wrapper import run_exec, DirMode
from util import (
    delete_children, move_children,
    hardlink_children, shuffle, expect_type, to_str, merge_env_vars,
    SubprocessError
)


result_bin = pathlib.Path("result").resolve() / "bin"
result_lib = result_bin.parent / "lib"


def get_results(
        prov_collectors: Sequence[ProvCollector],
        workloads: Sequence[Workload],
        iterations: int,
        seed: int,
        fail_first: bool = True,
) -> pandas.DataFrame:
    return (
        run_experiments_cached(
            prov_collectors,
            workloads,
            iterations=iterations,
            seed=seed,
            cache_dir=pathlib.Path(".cache"),
            big_temp_dir=pathlib.Path(".workdir"),
            size=256,
            fail_first=fail_first,
        )
        .assign(**{
            "n_ops": lambda df: list(map(len, df.operations)),
            "n_unique_files": lambda df: list(map(lambda ops: len({op.target0 for op in ops} | {op.target1 for op in ops}), df.operations)),
        })
    )


def run_experiments_cached(
        prov_collectors: Sequence[ProvCollector],
        workloads: Sequence[Workload],
        iterations: int,
        seed: int,
        cache_dir: pathlib.Path,
        big_temp_dir: pathlib.Path,
        size: int,
        fail_first: bool,
) -> pandas.DataFrame:
    key = (cache_dir / ("results_" + "_".join([
        *[prov_collector.name for prov_collector in prov_collectors],
        hashlib.sha256("".join(workload.name for workload in workloads).encode()).hexdigest()[:10],
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
            fail_first,
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
        fail_first: bool,
) -> pandas.DataFrame:
    prng = random.Random(seed)
    inputs = shuffle(
        prng,
        tuple(itertools.product(range(iterations), prov_collectors, workloads)),
    )
    big_temp_dir.mkdir(exist_ok=True, parents=True)
    temp_dir = big_temp_dir / "temp"
    log_dir = big_temp_dir / "log"
    artifacts_dir = big_temp_dir / "artifacts"
    work_dir = big_temp_dir / "work"
    temp_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)
    work_dir.mkdir(exist_ok=True)
    assert list(inputs)
    result_list = [
        (prov_collector, workload, run_one_experiment_cached(
            cache_dir, iteration, prov_collector, workload,
            work_dir, log_dir, temp_dir, artifacts_dir, size, fail_first,
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
                "operations": stats.operations,
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
    fail_first: bool,
) -> ExperimentStats:
    key = (cache_dir / ("_".join([
        urllib.parse.quote(prov_collector.name),
        urllib.parse.quote(workload.name),
        str(iteration)
    ]))).with_suffix(".pkl")
    if key.exists():
        return expect_type(ExperimentStats, pickle.loads(key.read_bytes()))
    else:
        delete_children(temp_dir)
        stats = run_one_experiment(
            iteration, prov_collector, workload, work_dir, log_dir,
            temp_dir, artifacts_dir, size, fail_first,
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
    artifacts_dir: pathlib.Path,
    size: int,
    fail_first: bool,
) -> ExperimentStats:
    with ch_time_block.ctx(f"setup {workload}"):
        try:
            workload.setup(work_dir)
        except SubprocessError as exc:
            print(str(exc))
            return ExperimentStats(
                cputime=0,
                walltime=0,
                memory=0,
                provenance_size=0,
                operations=(),
            )
        delete_children(log_dir)

    (temp_dir / "old_work_dir").mkdir()
    hardlink_children(work_dir, temp_dir / "old_work_dir")
    # We will restore temp_dir to this state after running the experiment

    with ch_time_block.ctx(f"setup {prov_collector}"):
        if prov_collector.requires_empty_dir:
            delete_children(work_dir)
            prov_collector.start(log_dir, size, work_dir)
            move_children(temp_dir / "old_work_dir", work_dir)
        else:
            prov_collector.start(log_dir, size, work_dir)
        cmd, env = workload.run(work_dir)
        main_executable = cmd[0]
        assert isinstance(main_executable, pathlib.Path)
        cmd = prov_collector.run(cmd, log_dir, size)
        cmd = (result_bin / "setarch", "--addr-no-randomize", *cmd)

    with ch_time_block.ctx(f"{workload} in {prov_collector}"):
        full_env = merge_env_vars(
            {
                "LD_LIBRARY_PATH": str(result_lib),
                "LIBRARY_PATH": str(result_lib),
                "PATH": str(result_bin),
                # "LD_PRELOAD": str(result_lib / "libfaketimeMT.so.1"),
                # "FAKETIME": "1970-01-01 00:00:00",
            },
            env,
        )
        stats = run_exec(
            cmd=cmd,
            env=full_env,
            dir_modes={
                work_dir: DirMode.FULL_ACCESS,
                log_dir: DirMode.FULL_ACCESS,
                pathlib.Path(): DirMode.READ_ONLY,
                pathlib.Path("/nix/store"): DirMode.READ_ONLY,
            },
        )
    move_children(temp_dir / "old_work_dir", work_dir)
    if fail_first and not stats.success:
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
