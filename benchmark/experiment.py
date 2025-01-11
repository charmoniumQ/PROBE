import shlex
import datetime
import rich.console
import dataclasses
import pathlib
import tempfile
import collections
import itertools
import util
import mandala.model
from mandala.imports import op, Ignore  # type: ignore
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

    records = []
    for iteration, collector, workload, verbose in util.progress.track(
            inputs,
            description="Collectors x Workloads"
    ):
        op = run_experiment(iteration, collector, workload, verbose)
        if verbose:
            util.console.print("=========")
            util.console.print(
                iteration,
                collector.name,
                workload.labels[0][-1],
                type(verbose).__name__,
                verbose.value, # type: ignore
            )
            util.console.print(
                type(op).__name__,
                op.hid,
                op.cid,
            )
            ctx = mandala.model.Context.current_context
            mandala.model.Context.current_context = None
            call = ctx.storage.get_ref_creator(op)
            mandala.model.Context.current_context = ctx
            if call:
                util.console.print(
                    type(call).__name__,
                    call.op.name,
                    call.hid,
                    call.cid,
                    call.semantic_version,
                    call.content_version,
                )
                for key, arg in call.inputs.items():
                    util.console.print(
                        "input",
                        key,
                        type(arg).__name__,
                        arg.cid,
                        arg.hid,
                        type(arg.obj).__name__,
                        arg,
                    )
                for key, arg in call.outputs.items():
                    util.console.print(
                        "output",
                        key,
                        type(arg).__name__,
                        arg.cid,
                        arg.hid,
                        arg.obj,
                        type(arg.obj).__name__,
                        arg,
                    )
        records.append(
            mandala.model.Context.current_context.storage.unwrap(
                op,
            )
        )

    df = polars.from_dicts(
        [
            {
                "collector": record.prov_collector.name,
                "workload_group": record.workload.labels[0][0],
                "workload_subgroup": record.workload.labels[0][1],
                "workload_subsubgroup": record.workload.labels[0][2],
                "workload_area": record.workload.labels[1][0],
                "workload_subarea": record.workload.labels[1][1],
                "seed": record.seed,
                "returncode": record.process_resources.returncode,
                "walltime": record.process_resources.walltime,
                "user_cpu_time": record.process_resources.user_cpu_time,
                "system_cpu_time": record.process_resources.system_cpu_time,
                "max_memory": record.process_resources.max_memory_usage,
                "n_voluntary_context_switches": record.process_resources.n_voluntary_context_switches,
                "n_involuntary_context_switches": record.process_resources.n_involuntary_context_switches,
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
    prov_collector: ProvCollector
    workload: Workload
    process_resources: measure_resources.CompletedProcess
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
            return proc, ExperimentStats(seed, prov_collector, workload, proc)
        else:
            proc = measure_resources.CompletedProcess()
            return proc, ExperimentStats(seed, prov_collector, workload, proc)


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
        seed,
        prov_collector,
        workload,
        workload_proc,
        provenance_size,
        len(ops),
        len({op.target0 for op in ops if op.target0} | {op.target1 for op in ops if op.target1}),
        collections.Counter(op.type for op in ops),
    )
