import numpy
import operator
import functools
import polars
import pathlib
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
        .pipe(lambda df: reduce_counts(df, "count_probe-slow_op_", "count_libcalls"))
        .pipe(lambda df: reduce_counts(df, "count_ptu_", "count_ptu_ops"))
        .rename({"count_probe-slow_count_procs": "count_procs", "count_probe-slow_count_execs": "count_execs"})
        .drop("count_probe-slow_count_tids")
    )
    counts = {
        (row["workload"], row["stage"]): {column: row[column] for column in counts_df.columns if column.startswith("counts_")}
        for row in counts_df.iter_rows(named=True)
    }
    with polars.Config(tbl_rows=100, tbl_cols=100):
        print(counts_df)
    avg_times_df = (
        df
          .group_by("workload", "tracer", "stage")
          .agg(
              polars.col("wall_time").mean().alias("mean_wall_time"),
              polars.col("wall_time").std(ddof=1).alias("std_wall_time"),
          )
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
    print(avg_times_df.select(
        "workload",
        "stage",
        "tracer",
        "overhead_diff",
        polars.col("overhead_ratio").log().alias("log_overhead_ratio"),
        (polars.col("count_syscalls") / (polars.col("unmod_mean_wall_time") / polars.duration(seconds=1))).alias("syscalls_per_sec"),
    ).sort("workload", "stage", "tracer"))
    for formula in [
            # "overhead ~ 1 + count_libcalls + count_procs + count_execs",
            # "overhead ~ 1 + count_procs + count_execs",
            # "overhead ~ 1 + count_execs",
            # "overhead ~ count_execs",
            "overhead_diff ~ 0 + count_libcalls",
            "overhead_diff ~ 0 + count_syscalls",
          ]:
        results = statsmodels.formula.api.ols(
            formula=formula,
            data=avg_times_df.filter(polars.col("tracer") == "probe-fast").with_columns(polars.col("overhead_diff") / polars.duration(seconds=1)).to_pandas(),
        ).fit()
        print(results.summary())
