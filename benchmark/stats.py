import datetime
import typing
import pathlib
import shutil
import polars
import util


workload_index = ("workload_group", "workload_subgroup", "workload_subsubgroup")
quantitative_vars = ("walltime", "user_cpu_time", "system_cpu_time", "max_memory", "n_involuntary_context_switches", "n_voluntary_context_switches")
too_quick_walltime = datetime.timedelta(seconds=1)


def _aggregate_iterations(iterations: polars.DataFrame) -> polars.DataFrame:
    def add_dummy(struct: typing.Mapping[str, float]) -> typing.Mapping[str, float]:
        # Parquet doesn't support 0-field structs.
        # InvalidOperationError: Unable to write struct type with no child field to Parquet. Consider adding a dummy child field.
        # So we will add a dummy field to empty structs
        if struct:
            return struct
        else:
            {"_dummy": 0.0}

    return iterations.group_by("collector", *workload_index).agg(
        *[
            polars.col(var).mean().alias(f"{var}_avg")
            for var in quantitative_vars
        ],
        polars.col("n_ops").mean().alias("n_ops_avg"),
        polars.col("n_unique_files").max().alias("n_unique_files_max"),
        polars.map_groups(
            exprs="op_counts",
            function=lambda op_countss: add_dummy({
                op: sum(
                    # some of op_counts[op] are set to None
                    util.expect_type(int, op_counts[op]) if op_counts.get(op) else 0
                    for op_counts in op_countss[0]
                ) / len(op_countss[0])
                for op in set(util.flatten1([op_counts.keys() for op_counts in op_countss[0]]))
            }),
            return_dtype=polars.Int32,
        ).alias("op_counts_avg"),
    )


def _get_workloads(agged: polars.DataFrame) -> polars.DataFrame:
    noprov_workloads = agged.filter(
        polars.col("collector") == "noprov"
    ).select(
        *workload_index,
        *[
            polars.col(f"{var}_avg").alias(f"noprov_{var}_avg")
            for var in quantitative_vars
        ],
    )
    strace_workloads = agged.filter(
        polars.col("collector") == "strace"
    )
    syscalls = sorted(
        field
        for field in strace_workloads["op_counts_avg"].struct.fields
        if strace_workloads["op_counts_avg"].struct.field(field).sum() != 0
    ) if not strace_workloads.is_empty() else []
    strace_workloads = strace_workloads.select(
        *workload_index,
        polars.col("n_ops_avg").alias("n_syscalls_avg"),
        polars.col("op_counts_avg").alias("syscalls").struct.rename_fields([f"syscall_{syscall}" for syscall in syscalls]),
    ).unnest("syscalls")

    return noprov_workloads.join(
        strace_workloads,
        on=workload_index,
        how="outer",
        # validate="1:1",
    ).drop([col + "_right" for col in workload_index])


def _add_overhead_columns(
        agged: polars.DataFrame,
        workloads: polars.DataFrame,
) -> polars.DataFrame:
    columns = agged.columns
    return agged.join(
        workloads,
        on=workload_index,
        how="outer",
        # validate="m:1",
    ).select(
        *columns,
        *[
            (polars.col(f"{var}_avg") / polars.col(f"noprov_{var}_avg")).alias(f"{var}_overhead_ratio")
            for var in quantitative_vars
        ],
        *[
            (polars.col(f"{var}_avg") - polars.col(f"noprov_{var}_avg")).alias(f"{var}_overhead_diff")
            for var in quantitative_vars
        ],
    )


def _print_diagnostics(
        iterations: polars.DataFrame,
        agged: polars.DataFrame,
        workloads: polars.DataFrame,
) -> None:
    _print_schema("Iterations DF", iterations.schema)
    _print_schema("Agged DF", agged.schema)
    _print_schema("Workloads DF", workloads.schema)

    summary = agged.pivot(
        "collector",
        index="workload_subsubgroup",
        values="walltime_avg",
    )
    print(summary.with_columns(
        *[
            dt_to_seconds(polars.col(col))
            for col in summary.columns
            if isinstance(summary.schema[col], polars.Duration)
        ]
    ))

    failures = iterations.filter(polars.col("returncode") != 0).select(
        "collector",
        "workload_subsubgroup",
    )
    if not failures.is_empty():
        print("Failures:", failures, sep="\n")
    too_quick = iterations.filter(polars.col("walltime") < too_quick_walltime).select(
        "collector",
        "workload_subsubgroup",
        "walltime",
    )
    if not too_quick.is_empty():
        print("Too quick:", too_quick, sep="\n")


def _print_schema(title: str | None, schema: polars.Schema) -> None:
    util.print_rich_table(
        title,
        ("Column", "DType"),
        [
            (name, str(dtype))
            for name, dtype in zip(schema.names(), schema.dtypes())
        ],
    )


def _save_data(
        iterations: polars.DataFrame,
        agged: polars.DataFrame,
        workloads: polars.DataFrame,
) -> None:
    output = pathlib.Path("output")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()

    iterations.write_parquet(output / "iterations.parquet")

    agged.write_parquet(output / "agged.parquet")

    agged.select(
        dt_to_seconds(polars.col(col)) if isinstance(dtype, polars.Duration) else
        polars.col(col).cast(str) if isinstance(dtype, polars.Categorical) else
        polars.col(col)
        for col, dtype in zip(agged.columns, agged.dtypes)
        if not isinstance(dtype, polars.Struct)
    ).write_csv(output / "agged.csv")

    workloads.write_parquet(output / "workloads.parquet")


def dt_to_seconds(series: polars.Expr, decimals: int = 1) -> polars.Expr:
    return (series.dt.total_nanoseconds() * 1e-9).round(decimals)


def process_df(iterations: polars.DataFrame) -> tuple[polars.DataFrame, polars.DataFrame]:
    _print_schema("Iterations DF", iterations.schema)
    agged = _aggregate_iterations(iterations)
    _print_schema("Agged DF", agged.schema)
    workloads = _get_workloads(agged)
    _print_schema("Workload DF", workloads.schema)
    agged = _add_overhead_columns(agged, workloads)
    _print_diagnostics(iterations, agged, workloads)
    _save_data(iterations, agged, workloads)
    return iterations, workloads
