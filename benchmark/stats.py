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
    return iterations.group_by("collector", *workload_index).agg(
        *[
            polars.col(var).mean().alias(f"{var}_avg")
            for var in quantitative_vars
        ],
        polars.col("n_ops").mean().alias("n_ops_avg"),
        polars.col("n_unique_files").max().alias("n_unique_files_max"),
        polars.map_groups(
            exprs="op_counts",
            function=lambda op_countss: {
                op: sum(
                    # some of op_counts[op] are set to None
                    util.expect_type(int, op_counts[op]) if op_counts.get(op) else 0
                    for op_counts in op_countss[0]
                ) / len(op_countss[0])
                for op in set(util.flatten1([op_counts.keys() for op_counts in op_countss[0]]))
            },
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
        validate="1:1",
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
        validate="m:1",
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


    with polars.Config(tbl_rows=-1, tbl_cols=-1):
        collectors = list(agged["collector"].unique())

        util.console.print("Absolute walltime")
        util.console.print(dt_as_seconds(agged.pivot(
            "collector",
            index="workload_subsubgroup",
            values="walltime_avg",
        )))

        util.console.print("Walltime overhead ratio")
        util.console.print(agged.pivot(
            "collector",
            index="workload_subsubgroup",
            values="walltime_overhead_ratio",
        ).with_columns(
            polars.col(collector).round(3)
            for collector in collectors
        ))

        # util.console.print("Walltime overhead difference")
        # util.console.print(dt_as_seconds(agged.pivot(
        #     "collector",
        #     index="workload_subsubgroup",
        #     values="walltime_overhead_diff",
        # )))

        failures = iterations.filter(polars.col("returncode") != 0).select(
            "seed",
            "collector",
            "workload_subsubgroup",
        )
        if not failures.is_empty():
            util.console.rule("[red]Failures:[/red]")
            util.console.print(str(failures))

        too_quick = iterations.filter(polars.col("walltime") < too_quick_walltime).select(
            "seed",
            "collector",
            "workload_subsubgroup",
            "walltime",
        )
        if not too_quick.is_empty():
            util.console.rule("[red]Too quick:[/red]")
            util.console.print(str(dt_as_seconds(too_quick)))


def _print_schema(title: str | None, schema: polars.Schema) -> None:
    util.console.print(title)
    with polars.Config(tbl_rows=-1):
        util.console.print(str(polars.DataFrame({"Column": schema.names(), "Dtypes": schema.dtypes()})))
    # util.print_rich_table(
    #     title,
    #     ("Column", "DType"),
    #     [
    #         (name, str(dtype))
    #         for name, dtype in zip(schema.names(), schema.dtypes())
    #     ],
    # )


def _save_data(
        iterations: polars.DataFrame,
        agged: polars.DataFrame,
        workloads: polars.DataFrame,
) -> None:
    output = pathlib.Path("output")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()

    parquet_safe_columns(iterations).write_parquet(output / "iterations.parquet")

    parquet_safe_columns(agged).write_parquet(output / "agged.parquet")

    csv_safe_columns(agged.with_columns()).write_csv(output / "agged.csv")

    parquet_safe_columns(workloads).write_parquet(output / "workloads.parquet")


def dt_as_seconds(df: polars.DataFrame, decimals: int = 1) -> polars.DataFrame:
    return df.with_columns(
        (polars.col(col).dt.total_nanoseconds() * 1e-9).round(decimals)
        for col, dtype in zip(df.columns, df.dtypes)
        if isinstance(dtype, polars.Duration)
    )


def csv_safe_columns(df: polars.DataFrame) -> polars.DataFrame:
    return dt_as_seconds(df).select(
        polars.col(col).cast(str) if isinstance(dtype, polars.Categorical) else
        polars.col(col)
        for col, dtype in zip(df.columns, df.dtypes)
        if not isinstance(dtype, polars.Struct)
    )


def parquet_safe_columns(df: polars.DataFrame) -> polars.DataFrame:
    # Parquet doesn't support 0-field structs.
    # InvalidOperationError: Unable to write struct type with no child field to Parquet. Consider adding a dummy child field.
    # So we will add a dummy field to empty structs
    return df.with_columns(
        polars.col(col).struct.with_fields(_dummy=0)
        for col, dtype in zip(df.columns, df.dtypes)
        if isinstance(dtype, polars.Struct) and not df[col].struct.fields
    )


def process_df(iterations: polars.DataFrame) -> tuple[polars.DataFrame, polars.DataFrame]:
    agged = _aggregate_iterations(iterations)
    workloads = _get_workloads(agged)
    agged = _add_overhead_columns(agged, workloads)
    _print_diagnostics(iterations, agged, workloads)
    _save_data(iterations, agged, workloads)
    return iterations, workloads
