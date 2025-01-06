import functools
import operator
import collections
import polars


def process_df(iterations: polars.DataFrame) -> tuple[polars.DataFrame, polars.DataFrame]:
    workload_index = "workload_group", "workload_subgroup", "workload_subsubgroup"
    noprov_workloads = iterations.filter(
        polars.col("collector") == "noprov"
    ).group_by(workload_index).agg(
        polars.col("workload_area").first(),
        polars.col("workload_subarea").first(),
        polars.col("walltime").mean(),
        polars.col("user_cpu_time").mean(),
        polars.col("system_cpu_time").mean(),
        polars.col("max_memory").mean(),
        polars.col("n_voluntary_context_switches").mean(),
        polars.col("n_involuntary_context_switches").mean(),
    )
    strace_workloads = iterations.filter(
        polars.col("collector") == "strace"
    ).group_by(workload_index).agg(
        polars.col("n_ops").max(),
        polars.col("n_unique_files").max(),
        polars.map_groups(
            exprs="op_counts",
            function=lambda op_countss: functools.reduce(
                operator.add,
                [
                    collections.Counter({
                        op: count
                        for op, count in op_counts.items()
                        if count is not None
                    })
                    for op_counts in op_countss[0]
                ],
                collections.Counter(),
            ),
            return_dtype=polars.Int32,
        ).alias("op_counts"),
    )
    workloads = noprov_workloads.join(
        strace_workloads,
        on=workload_index,
        how="outer",
        # validate="1:1",
    ).drop([col + "_right" for col in workload_index])

    quantitative_vars = ["walltime", "user_cpu_time", "system_cpu_time", "max_memory", "n_involuntary_context_switches", "n_voluntary_context_switches"]
    iteration_columns = iterations.columns
    iterations = iterations.join(
        workloads.select(
            *workload_index,
            *[polars.col(var).alias(f"noprov_{var}") for var in quantitative_vars]
        ),
        on=workload_index,
        how="outer",
        # validate="m:1",
    ).select(
        *iteration_columns,
        *[
            (polars.col(var) / polars.col(f"noprov_{var}")).alias(f"{var}_overhead_ratio")
            for var in quantitative_vars
        ],
        *[
            (polars.col(var) - polars.col(f"noprov_{var}")).alias(f"{var}_overhead_diff")
            for var in quantitative_vars
        ],
    )

    return iterations, workloads
