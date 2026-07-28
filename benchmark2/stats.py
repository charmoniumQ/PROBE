import operator
import functools
import pathlib
import textwrap
import polars
import statsmodels.api


root_dir = pathlib.Path(__file__).resolve().parent.parent.resolve()
results_dir = root_dir / ".results"
results_file = results_dir / "db.parquet"


def reduce_counts(df: polars.DataFrame, col_prefix: str, name: str) -> polars.DataFrame:
    selected_columns = [column for column in df.columns if column.startswith(col_prefix)]
    return (
        df
        .with_columns(functools.reduce(operator.add, [polars.col(column) for column in selected_columns]).alias(name))
        .drop(selected_columns)
    )


if __name__ == "__main__":
    polars.Config().set_tbl_rows(100)
    polars.Config().set_tbl_cols(10)

    df = polars.read_parquet(results_file)

    counts_df = (
        df
        .explode("op_counts")
        .unnest("op_counts", separator=":")
        .filter(~polars.col("op_counts:key").is_null())
        .with_columns(
            ("count_" + polars.col("tracer") + "_" + polars.col("op_counts:key")).alias("op_counts:key")
        )
        .pivot("op_counts:key", values="op_counts:value", index=("tracer", "workload", "stage"), aggregate_function="mean")
        .group_by("workload", "stage")
        .sum()
        .pipe(lambda df: reduce_counts(df, "count_strace_", "count_syscalls"))
        #.pipe(lambda df: reduce_counts(df, "count_probe-slow_op_", "count_libcalls"))
        .pipe(lambda df: reduce_counts(df, "count_ptu_", "count_ptu_ops"))
        #.rename({"count_probe-slow_count_procs": "count_procs", "count_probe-slow_count_execs": "count_execs"})
        #.drop("count_probe-slow_count_tids")
    )
    counts = {
        (row["workload"], row["stage"]): {column: row[column] for column in counts_df.columns if column.startswith("counts_")}
        for row in counts_df.iter_rows(named=True)
    }
    print("Counts:")
    print([column for column in counts_df.columns if column.startswith("counts_")])
    # with polars.Config(tbl_rows=100, tbl_cols=100):
    #     print(counts_df)
    avg_times_df = (
        df
          .group_by("workload", "tracer", "stage")
          .agg([
              *[
                  polars.col(col).mean().alias(f"mean_{col}")
                  for col in ["wall_time", "user_time", "kernel_time"]
              ],
              *[
                  polars.col(col).std(ddof=1).alias(f"std_{col}")
                  for col in ["wall_time", "user_time", "kernel_time"]
              ],
          ])
          .sort("mean_wall_time")
          .pipe(lambda df: df.join(
              (
                  df.filter(polars.col("tracer") == "none")
                  .select(
                      "workload",
                      "stage",
                      polars.col("mean_wall_time").alias("unmod_mean_wall_time")
                  )
              ),
              on=("workload", "stage")
          ))
          .with_columns((polars.col("mean_wall_time") - polars.col("unmod_mean_wall_time")).alias("overhead_diff"))
          .with_columns((polars.col("mean_wall_time") / polars.col("unmod_mean_wall_time")).alias("overhead_ratio"))
          .join(counts_df, on=("workload", "stage"), how="full")
    )
    avg_wall_times_df = avg_times_df.filter(polars.col("tracer").eq("none")).drop("tracer").filter(polars.col("mean_wall_time").ge(polars.duration(seconds=1)))
    print(avg_wall_times_df.select(
        "workload",
        "stage",
        polars.col("mean_wall_time") / polars.duration(seconds=1),
        polars.col("mean_user_time") / polars.duration(seconds=1),
        polars.col("mean_kernel_time") / polars.duration(seconds=1),
    ))
    workloads_df = avg_wall_times_df.select("workload", "stage")
    # avg_wall_times_df.filter(polars.struct(polars.col("workload"), polars.col("stage")))
    print(
        avg_times_df
        .select(
            "workload",
            "stage",
            "tracer",
            "overhead_ratio",
            polars.col("overhead_ratio").log(base=2).alias("log_overhead_ratio"),
        )
        .unpivot(
            ("overhead_ratio", "log_overhead_ratio"),
            variable_name="metric",
            index=("workload", "stage", "tracer"),
        )
        .pivot(
            "tracer",
            index=("workload", "stage", "metric"),
            values="value"
        )
        .sort("workload", "stage", "metric")
        .drop("metric")
    )
    print(
        avg_times_df
        .filter(polars.col("tracer").ne("none"))
        .select(
            "workload",
            "stage",
            "tracer",
            (polars.col("overhead_ratio") * 100 - 100).round().cast(polars.Int16),
        )
        .pivot(
            "tracer",
            index=("workload", "stage"),
            values="overhead_ratio"
        )
        .sort("workload", "stage")
        .style
        .as_latex()
    )
    for formula in [
            # "overhead_diff ~ 0 + tracer:count_rzip_executed_files",
            # "overhead_diff ~ 1 + tracer:count_rzip_executed_files",
            # "overhead_diff ~ 0 + tracer:count_syscalls + tracer:count_rzip_executed_files",
            # "overhead_diff ~ 1 + tracer:count_syscalls + tracer:count_rzip_executed_files",
            "overhead_diff ~ 0 + tracer:count_syscalls",
            # "overhead_diff ~ 1 + tracer:count_syscalls",
          ]:
        results = statsmodels.formula.api.ols(
            formula=formula,
            data=(
                avg_times_df
                .filter(polars.col("tracer").ne("none"))
                .filter(polars.col("overhead_diff").ge(0))
                .with_columns(polars.col("overhead_diff") / polars.duration(microseconds=1))
                .to_pandas()
            ),
        ).fit()
        print(f"{formula} {results.rsquared * 100:.0f}% R-squared")
        print(textwrap.indent(str(results.summary()), prefix="  "))
        print("---------")
