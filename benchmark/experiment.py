import shlex
import datetime
import rich.console
import dataclasses
import pathlib
import tempfile
import collections
import itertools
import util
import gc
import psutil
from pympler.asizeof import asizeof as size
from mandala.imports import op, Ignore, Storage  # type: ignore
import rich.progress
from workloads import Workload
from prov_collectors import ProvCollector
import measure_resources
# on my machine, importing polars before the others causes a segfault
# https://github.com/NixOS/nixpkgs/issues/326230
# TODO: Debug this
import polars


def run_experiments(
        prov_collectors: list[ProvCollector],
        workloads: list[Workload],
        iterations: int,
        seed: int,
        verbose: bool,
        rerun: bool,
        storage_file: pathlib.Path,
) -> polars.DataFrame:
    if verbose:
        util.print_rich_table(
            "run_experiments",
            ("Variable", "Value"),
            [
                ("prov_collectors", f"({len(prov_collectors)}) {', '.join(collector.name for collector in prov_collectors)}"),
                ("workloads", f"({len(workloads)}) {', '.join(workload.labels[0][2] for workload in workloads)}"),
                ("iterations", iterations),
                ("seed", seed),
                ("rerun", rerun),
            ],
        )
    start = datetime.datetime.now()
    inputs = list(itertools.chain.from_iterable(
        # Shuffling eliminates confounding effects of order dependency
        # E.g., if the CPU overheats and gets throttled, then later runs will be slower
        # We try to prevent this, but if other order effects leak through, at least we randomize the order.
        # However, all iteration=0 come before iteration=1, so that if you stop the program before finishing all n iterations, it may be able to completely finished m < n iterations.
        util.shuffle(
            # each iteration is shuffled using a different seed
            iteration ^ seed,
            tuple(itertools.product(
                [iteration ^ seed],
                prov_collectors,
                workloads,
                [Ignore(verbose)],
            )),
        )
        for iteration in range(iterations)
    ))


    process = psutil.Process()
    last_used_mem = process.memory_info().rss
    records = []
    br = util.fmt_bytes
    with Storage(storage_file) as storage:
        for iteration, collector, workload, verbose in util.progress.track(
                inputs,
                description="Collectors x Workloads"
        ):
            op = run_experiment(iteration, collector, workload, verbose)
            record = storage.unwrap(op)
            storage.commit()
            records.append(record)
            if verbose:
                record_size = size(record)
                util.console.print(
                    f"  Records: {br(size(records))} ≅ {br(record_size * len(records))} = {len(records)} x {br(record_size, 1)}",
                )
                util.console.print(f"  Storage: {br(size(storage))}")
                used_mem = process.memory_info().rss
                util.console.print(f"  Total: {br(used_mem)} (incrase of {br(used_mem - last_used_mem)} from last time)")
                util.console.print(f"  Free: {br(psutil.virtual_memory().available)}")
                util.console.print(f"  Op cmd max memory usage: {br(record.max_memory)}")
                last_used_mem = used_mem

    df = polars.from_dicts(
        [
            {
                "collector": record.prov_collector,
                "workload_group": record.workload_group,
                "workload_subgroup": record.workload_subgroup,
                "workload_subsubgroup": record.workload_subsubgroup,
                "workload_area": record.workload_area,
                "workload_subarea": record.workload_subarea,
                "seed": record.seed,
                "returncode": record.returncode,
                "walltime": record.walltime,
                "user_cpu_time": record.user_cpu_time,
                "system_cpu_time": record.system_cpu_time,
                "max_memory": record.max_memory,
                "n_voluntary_context_switches": record.n_voluntary_context_switches,
                "n_involuntary_context_switches": record.n_involuntary_context_switches,
                "provenance_size": record.provenance_size,
                "n_ops": record.n_ops,
                "n_unique_files": record.n_unique_files,
                "op_counts": record.op_counts,
            }
            for record in records
        ],
        schema_overrides={
            "collector": polars.Categorical,
            "workload_group": polars.Categorical,
            "workload_subgroup": polars.Categorical,
            "workload_subsubgroup": polars.Categorical,
            "workload_area": polars.Categorical,
            "workload_subarea": polars.Categorical,
        },
    )
    util.console.print(f"run_experiment all inputs in {(datetime.datetime.now() - start).total_seconds():.1f}")
    return df


@dataclasses.dataclass
class ExperimentStats:
    seed: int
    prov_collector: str
    workload_group: str
    workload_subgroup: str
    workload_subsubgroup: str
    workload_area: str
    workload_subarea: str
    returncode: int = -1
    walltime: datetime.timedelta = datetime.timedelta()
    user_cpu_time: datetime.timedelta = datetime.timedelta()
    system_cpu_time: datetime.timedelta = datetime.timedelta()
    max_memory: int = 0
    n_involuntary_context_switches: int = 0
    n_voluntary_context_switches: int = 0
    provenance_size: int = 0
    n_ops: int = 0
    n_unique_files: int = 0
    op_counts: collections.Counter[str] = dataclasses.field(default_factory=collections.Counter[str])


@op
def run_experiment(
    seed: int,
    prov_collector: ProvCollector,
    workload: Workload,
    verbose: bool,
) -> ExperimentStats:
    if verbose:
        util.console.rule(f"{prov_collector.name} {workload.labels[0][-1]}")

    setup_teardown_timeout = datetime.timedelta(seconds=30)
    labels = (seed, prov_collector.name, workload.labels[0][0], workload.labels[0][1], workload.labels[0][2], workload.labels[1][0], workload.labels[1][1])

    def run_proc(
            cmd: tuple[str, ...],
            timeout: datetime.timedelta | None,
    ) -> tuple[measure_resources.CompletedProcess, ExperimentStats]:
        if cmd:
            if not cmd[0].startswith("/nix/store"):
                raise RuntimeError(f"Subprocess binaries should be absolute (generated by Nix) not {cmd[0]}")
            if verbose:
                str_cmd = shlex.join(cmd).replace(
                    str(work_dir.resolve()), "$work_dir",
                ).replace(
                    str(prov_log.resolve()), "$work_dir/../prov",
                )
                util.console.print(f"env --chdir $work_dir - {str_cmd}")
            proc = measure_resources.measure_resources(
                cmd,
                cwd=work_dir,
                env={},
                timeout=timeout,
            )
            if verbose:
                util.console.print(f"{proc.walltime.total_seconds():.1f}sec")
                if proc.returncode != 0:
                    util.console.print(rich.padding.Padding(
                        proc.stdout.decode(errors="surrogateescape").strip(),
                        (1, 4),
                    ))
                    util.console.print(rich.padding.Padding(
                        proc.stderr.decode(errors="surrogateescape").strip(),
                        (1, 4),
                    ))
            return proc, ExperimentStats(*labels, returncode=proc.returncode)
        else:
            proc = measure_resources.CompletedProcess()
            return proc, ExperimentStats(*labels)


    with tempfile.TemporaryDirectory() as _tmp_dir:
        tmp_dir = pathlib.Path(_tmp_dir).resolve()
        work_dir = tmp_dir / "work"
        prov_log = tmp_dir / "prov"

        work_dir.mkdir(exist_ok=True, parents=False)

        if verbose:
            util.console.print(f"work_dir={tmp_dir!s} && rm -rf $work_dir && mkdir --parents $work_dir")

        context = {
            "work_dir": str(work_dir),
            "prov_log": str(prov_log),
        }

        proc, exp_stats = run_proc(
            prov_collector.setup_cmd.expand(context),
            setup_teardown_timeout,
        )
        if proc.returncode != 0:
            return exp_stats

        proc, exp_stats = run_proc(
            workload.setup_cmd.expand(context),
            setup_teardown_timeout,
        )
        if proc.returncode != 0:
            return exp_stats

        workload_cmd = workload.cmd.expand(context)
        workload_proc, exp_stats = run_proc(
            prov_collector.run_cmd.expand(context) + workload_cmd,
            timeout=workload.timeout * prov_collector.timeout_multiplier if workload.timeout else None,
        )
        if workload_proc.returncode != 0:
            return exp_stats

        proc, exp_stats = run_proc(
            prov_collector.teardown_cmd.expand(context),
            setup_teardown_timeout,
        )
        if proc.returncode != 0:
            return exp_stats

        provenance_size = (util.dir_size(prov_log) if prov_log.is_dir() else prov_log.stat().st_size) if prov_log.exists() else 0
        ops = prov_collector.count(prov_log, pathlib.Path(workload_cmd[0]))

    return ExperimentStats(
        *labels,
        returncode=workload_proc.returncode,
        walltime=workload_proc.walltime,
        user_cpu_time=workload_proc.user_cpu_time,
        system_cpu_time=workload_proc.system_cpu_time,
        max_memory=workload_proc.max_memory_usage,
        n_involuntary_context_switches=workload_proc.n_involuntary_context_switches,
        n_voluntary_context_switches=workload_proc.n_voluntary_context_switches,
        provenance_size=provenance_size,
        n_ops=len(ops),
        n_unique_files=len({op.target0 for op in ops if op.target0} | {op.target1 for op in ops if op.target1}),
        op_counts=collections.Counter(op.type for op in ops),
    )
