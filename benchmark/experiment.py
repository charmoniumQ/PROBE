from __future__ import annotations
import json
import asyncio
import textwrap
import shlex
import datetime
import shutil
import typing
import dataclasses
import pathlib
import collections
import itertools
import dbus_watcher
import dbus_next
import util
from workloads import WORKLOADS, Workload
from prov_collectors import PROV_COLLECTORS, ProvCollector
from mandala.imports import op, Ignore, Storage  # type: ignore
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
        internal_cache: pathlib.Path,
        parquet_output: pathlib.Path,
        total_warmups: int,
        machine_id: int,
        orig_df: polars.DataFrame | None,
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
                ("total warmups", total_warmups),
            ],
        )
    inputs = list(itertools.chain.from_iterable(
        # Shuffling eliminates confounding effects of order dependency
        # E.g., if the CPU overheats and gets throttled, then later runs will be slower
        # We try to prevent this, but if other order effects leak through, at least we randomize the order.
        # However, all iteration=0 come before iteration=1, so that if you stop the program before finishing all n iterations, it may be able to completely finished m < n iterations.
        util.shuffle(
            # each iteration is shuffled using a different seed
            iteration + seed,
            tuple(itertools.product(
                [iteration + seed],
                prov_collectors,
                workloads,
            )),
        )
        for iteration in range(iterations)
    ))


    records = []
    with Storage(internal_cache) as storage:
        for iteration, collector, workload in util.progress.track(
                inputs,
                description="Collectors x Workloads"
        ):
            if collector.name == "noprovstable" and workload.labels[0][-1] in {"pw-01", "pp-01"}:
                continue
            op = run_experiment_warmups(iteration, collector, workload, total_warmups, machine_id, Ignore(verbose))
            t_records = storage.unwrap(op)
            storage.commit()
            records.extend(t_records)
            df = util.parquet_safe_columns(polars.from_dicts(
                [
                    {
                        "collector": record.prov_collector,
                        "workload_group": record.workload_group,
                        "workload_subgroup": record.workload_subgroup,
                        "workload_subsubgroup": record.workload_subsubgroup,
                        "seed": record.seed,
                        "returncode": record.returncode,
                        "walltime": record.walltime,
                        "user_cpu_time": record.user_cpu_time,
                        "system_cpu_time": record.system_cpu_time,
                        "max_memory": record.max_memory,
                        "provenance_size": record.provenance_size,
                        "n_ops": record.n_ops,
                        "n_unique_files": record.n_unique_files,
                        "op_counts": record.op_counts,
                        "n_warmups": record.warmups,
                        "machine_id": record.machine_id,
                        "iteration": iteration,
                    }
                    for record in records
                ],
                schema_overrides={
                    "collector": polars.Enum(sorted({
                        collector.name
                        for collector in PROV_COLLECTORS
                    })),
                    "workload_group": polars.Enum(sorted({
                        workload.labels[0][0]
                        for workload in WORKLOADS
                    })),
                    "workload_subgroup": polars.Enum(sorted({
                        workload.labels[0][1]
                        for workload in WORKLOADS
                    })),
                    "workload_subsubgroup": polars.Enum(sorted({
                        workload.labels[0][2]
                        for workload in WORKLOADS
                    })),
                },
            ))
            if orig_df is not None:
                new_op_count_fields = {
                    field.name
                    for field in util.expect_type(polars.Struct, df.schema["op_counts"]).fields
                }
                orig_op_count_fields = {
                    field.name
                    for field in util.expect_type(polars.Struct, orig_df.schema["op_counts"]).fields
                }
                combined_op_count_fields = sorted(new_op_count_fields | orig_op_count_fields)
                orig_df = orig_df.with_columns(
                    polars.struct(
                        polars.col("op_counts").struct.field(field) if field in orig_op_count_fields else polars.lit(0, dtype=polars.Int64).alias(field)
                        for field in combined_op_count_fields
                    ).alias("op_counts")
                )
                df = df.with_columns(
                    polars.struct(
                        polars.col("op_counts").struct.field(field) if field in new_op_count_fields else polars.lit(0, dtype=polars.Int64).alias(field)
                        for field in combined_op_count_fields
                    ).alias("op_counts")
                )
                for key in (orig_df.schema.keys() | df.schema.keys()):
                    old_type = orig_df.schema.get(key)
                    new_type = df.schema.get(key)
                    print(
                        key,
                        old_type == new_type if old_type and new_type else False,
                        old_type,
                        new_type,
                    )
                df = polars.concat((orig_df, df))
            df.write_parquet(parquet_output)
    return df


def drop_calls(
        internal_cache: pathlib.Path,
        seed: int,
        iterations: int,
        collectors: list[ProvCollector],
        workloads: list[Workload],
        total_warmups: int,
        machine_id: int,
) -> None:
    ops = []
    with Storage(internal_cache) as storage:
        ops.extend([
            run_experiment_warmups(seed + iteration, collector, workload, total_warmups, machine_id, Ignore(False))
            for collector in collectors
            for workload in workloads
            for iteration in range(iterations)
        ])
    storage.drop_calls(
        [storage.get_ref_creator(op) for op in ops],
        delete_dependents=True,
    )


@dataclasses.dataclass
class Resources:
    cpu_user_us: int = 0
    cpu_system_us: int = 0
    peak_memory_usage: int = 0
    walltime_us: int = 0
    returncode: int = 0
    signal: int = 0
    stdout: bytes = b""
    stderr: bytes = b""


@dataclasses.dataclass
class ExperimentStats:
    seed: int = 0
    prov_collector: str = ""
    workload_group: str = ""
    workload_subgroup: str = ""
    workload_subsubgroup: str = ""
    returncode: int = -1
    walltime: datetime.timedelta = datetime.timedelta()
    user_cpu_time: datetime.timedelta = datetime.timedelta()
    system_cpu_time: datetime.timedelta = datetime.timedelta()
    max_memory: int = 0
    provenance_size: int = 0
    n_ops: int = 0
    n_unique_files: int = 0
    op_counts: collections.Counter[str] = dataclasses.field(default_factory=collections.Counter[str])
    warmups: int = 0
    machine_id: int = 0


@op
def run_experiment_warmups(
    seed: int,
    prov_collector: ProvCollector,
    workload: Workload,
    total_warmups: int,
    machine_id: int,
    verbose: bool,
) -> list[ExperimentStats]:
    return asyncio.run(async_run_experiment_warmups(
        seed,
        prov_collector,
        workload,
        total_warmups,
        machine_id,
        verbose,
    ))


async def async_run_experiment_warmups(
    seed: int,
    prov_collector: ProvCollector,
    workload: Workload,
    total_warmups: int,
    machine_id: int,
    verbose: bool,
) -> list[ExperimentStats]:
    # If ACPI suspend detected during any run, we should redo all.
    # We use async so we can listen to acpi events while the process is running
    while True:
        suspend_event = dbus_watcher.DbusWatcher(
            dbus_next.BusType.SYSTEM,
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            "prepare_for_sleep",
        )
        async with suspend_event:
            ret = []
            for warmup in range(total_warmups):
                ret.append(await run_experiment(
                    seed,
                    prov_collector,
                    workload,
                    warmup,
                    machine_id,
                    verbose,
                ))
        if suspend_event.signals:
            util.console.print("[yellow]System suspended during benchmarking; re-doing")
        else:
            return ret

async def run_experiment(
    seed: int,
    prov_collector: ProvCollector,
    workload: Workload,
    warmups: int,
    machine_id: int,
    verbose: bool,
) -> ExperimentStats:
    # 1. Setup collector
    # 2. setup benchmark
    # 3. prov collect benchmark
    # 4. teardown benchmark
    # 5. teardown collector
    if verbose:
        util.console.rule(f"{prov_collector.name} {workload.labels[0][-1]} {warmups}")

    setup_teardown_timeout = datetime.timedelta(seconds=10)

    stats = ExperimentStats(
        seed=seed,
        prov_collector=prov_collector.name,
        workload_group=workload.labels[0][0],
        workload_subgroup=workload.labels[0][1],
        workload_subsubgroup=workload.labels[0][2],
        warmups=warmups,
        machine_id=machine_id,
    )

    tmp_dir = pathlib.Path("/tmp/probe-benchmark")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    work_dir = tmp_dir / "work"
    prov_dir = tmp_dir / "prov"

    prov_dir.mkdir(exist_ok=True, parents=True)
    work_dir.mkdir(exist_ok=True, parents=False)

    if verbose:
        # Print an equivalent command that we can copy/paste
        util.console.print(f"work_dir={work_dir!s} && prov_dir={prov_dir!s}")
        util.console.print("rm -rf $work_dir $prov_dir && mkdir --parents $work_dir $prov_dir")

    context = {
        "work_dir": str(work_dir),
        "prov_dir": str(prov_dir),
    }

    proc = await run(
        prov_collector.setup_cmd.expand(context),
        work_dir,
        tmp_dir,
        setup_teardown_timeout,
        verbose,
    )
    if proc.returncode != 0:
        return stats

    proc = await run(
        workload.setup_cmd.expand(context),
        work_dir,
        tmp_dir,
        setup_teardown_timeout,
        verbose,
    )
    if proc.returncode != 0:
        return stats

    workload_cmd = workload.cmd.expand(context)
    workload_proc = await run(
        prov_collector.run_cmd.expand(context) + workload_cmd,
        work_dir,
        tmp_dir,
        workload.timeout * prov_collector.timeout_multiplier if workload.timeout else None,
        verbose,
        # Clear cache only on first warmup iter
        clear_cache=warmups == 0,
    )

    proc = await run(
        prov_collector.teardown_cmd.expand(context),
        work_dir,
        tmp_dir,
        setup_teardown_timeout,
        verbose,
    )
    if proc.returncode != 0:
        return stats

    provenance_size = util.dir_size(prov_dir)
    ops = prov_collector.count(prov_dir, pathlib.Path(workload_cmd[0]))

    return dataclasses.replace(
        stats,
        returncode=workload_proc.returncode,
        walltime=datetime.timedelta(microseconds=workload_proc.walltime_us),
        user_cpu_time=datetime.timedelta(microseconds=workload_proc.cpu_user_us),
        system_cpu_time=datetime.timedelta(microseconds=workload_proc.cpu_system_us),
        max_memory=workload_proc.peak_memory_usage,
        provenance_size=provenance_size,
        n_ops=len(ops),
        n_unique_files=len({op.target0 for op in ops if op.target0} | {op.target1 for op in ops if op.target1}),
        op_counts=collections.Counter(op.type for op in ops),
    )



setuid_benchmark_utils = pathlib.Path().resolve() / "benchmark_utils"
benchmark_utils = pathlib.Path().resolve() / "benchmark_utils/target/debug"
async def run(
        cmd: list[str],
        work_dir: pathlib.Path,
        tmp_dir: pathlib.Path,
        timeout: datetime.timedelta | None,
        verbose: bool,
        clear_cache: bool = False,
) -> Resources:
    if not cmd:
        # It is a programming convenience to accept an empty list,
        # treating it as a noop that consumes no resources.
        return Resources()
    resource_json = tmp_dir / "time.json"
    # TODO: Choose this smartly
    cpus = [3]
    command = [
            str(setuid_benchmark_utils / "systemd_shield"),
            f"--cpus={','.join(map(str, cpus))}",
            *([
                f"--cpu-seconds={int(timeout.total_seconds() * len(cpus)) + 1}"
            ] if timeout is not None else []),
            # "--mem_bytes=",
            "--swap-mem-bytes=0",
            "--nice=-20",
            "--clear-env",
            "--",
            str(setuid_benchmark_utils / "stabilize"),
            f"--config={setuid_benchmark_utils / 'pre_benchmark_config.json'!s}",
            f"--cpus={','.join(map(str, cpus))}",
            *(["--drop-file-cache"] if clear_cache else []),
            "--",
            str(benchmark_utils / "systemd_time"),
            f"--output={resource_json!s}",
            "--",
            *cmd,
        ]
    str_command = shlex.join(command)
    if verbose:
        util.console.print(str_command)

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=work_dir,
        env={},
    )
    stdout, stderr = await proc.communicate()
    returncode = await proc.wait()

    resources = typing.cast(Resources, Resources(**{
        **(json.loads(resource_json.read_text()) if resource_json.exists() else {}),
        "stdout": stdout,
        "stderr": stderr,
    }))
    if returncode != 0:
        if not verbose:
            # If verbose, we already printed this.
            # If not verbose, we should do so now.
            util.console.print(f"Command failed: env --chdir $work_dir - {str_command}")
        print(textwrap.indent(
            resources.stdout.decode(errors="surrogateescape").strip(),
            "  ",
        ))
        print(textwrap.indent(
            resources.stderr.decode(errors="surrogateescape").strip(),
            "  ",
        ))
    if verbose:
        util.console.print(f"{resources.walltime_us / 1e6:.1f}sec")
    return resources
