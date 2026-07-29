import functools
import operator
import pathlib
import textwrap
import matplotlib.figure
import polars
import scikit_posthocs
import scipy.stats
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

    MIN_TIME_CUTOFF = 2.0
    FRACTION_OF_ORIG_CUTOFF = 0.75
    MEAN_TO_STD_UNMOD_CUTOFF = 0.4
    MEASUREMENT = ["wall_time", "user_time", "kernel_time"]
    MAIN_MEASURE = "wall_time"
    avg_times_df = (
        df
          .group_by("workload", "tracer", "stage")
          .agg([
              *[
                  (polars.col(col) / polars.duration(seconds=1)).log().mean().alias(f"mean_log_{col}")
                  for col in MEASUREMENT
              ],
              *[
                  (polars.col(col) / polars.duration(seconds=1)).log().std().alias(f"std_log_{col}")
                  for col in MEASUREMENT
              ],
          ])
          .with_columns(
              *[
                  polars.col(f"mean_log_{col}").exp().alias(f"mean_{col}")
                  for col in MEASUREMENT
              ],
              *[
                  ((polars.col(f"mean_log_{col}") + polars.col(f"std_log_{col}") / 2).exp()
                   - 
                   (polars.col(f"mean_log_{col}") - polars.col(f"std_log_{col}") / 2).exp()
                   ).alias(f"std_{col}")
                  for col in MEASUREMENT
              ],
          )
          .pipe(lambda df: df.join(
              (
                  df.filter(polars.col("tracer").eq("none"))
                  .select(
                      "workload",
                      "stage",
                      *[
                          polars.col(f"mean_log_{col}").alias(f"unmod_mean_log_{col}")
                          for col in MEASUREMENT
                      ],
                      *[
                          polars.col(f"std_log_{col}").alias(f"unmod_std_log_{col}")
                          for col in MEASUREMENT
                      ],
                      *[
                          polars.col(f"mean_{col}").alias(f"unmod_mean_{col}")
                          for col in MEASUREMENT
                      ],
                      *[
                          polars.col(f"std_{col}").alias(f"unmod_std_{col}")
                          for col in MEASUREMENT
                      ],
                  )
              ),
              on=("workload", "stage")
          ))
          .with_columns(
              *[
                  (polars.col(f"mean_log_{col}") - polars.col(f"unmod_mean_log_{col}")).alias(f"mean_log_{col}_overhead")
                  for col in MEASUREMENT
              ],
              *[
                  ((polars.col(f"std_log_{col}")**2 + polars.col(f"unmod_std_log_{col}")**2)**.5).alias(f"std_log_{col}_overhead")
                  for col in MEASUREMENT
              ],
          )
          .filter(polars.col("tracer").ne("none"))
          .join(counts_df, on=("workload", "stage"), how="full")
          .filter(polars.col(f"mean_{MAIN_MEASURE}") > FRACTION_OF_ORIG_CUTOFF * polars.col(f"unmod_mean_{MAIN_MEASURE}"))
          .filter(polars.col(f"unmod_mean_{MAIN_MEASURE}").ge(MIN_TIME_CUTOFF))
          .filter(polars.col(f"unmod_std_{MAIN_MEASURE}") / polars.col(f"unmod_mean_{MAIN_MEASURE}") < MEAN_TO_STD_UNMOD_CUTOFF)
          .pipe(lambda df: [print(df.select(
              "workload",
              "stage",
              polars.col(f"unmod_mean_log_{MAIN_MEASURE}").exp(),
          )), df][1])
          .with_columns(
              polars.col(f"mean_log_{MAIN_MEASURE}_overhead").exp().alias("est_overhead"),
              ((polars.col(f"mean_log_{MAIN_MEASURE}_overhead") + polars.col(f"std_log_{MAIN_MEASURE}_overhead") / 2).exp()
               - 
               (polars.col(f"mean_log_{MAIN_MEASURE}_overhead") - polars.col(f"std_log_{MAIN_MEASURE}_overhead") / 2).exp()
               ).alias("err_overhead"),
          )
          .with_columns(
              ((polars.col("est_overhead") - 1) * 100).alias("est_overhead_%"),
              (polars.col("err_overhead") * 100).alias("err_overhead_%")
          )
    )

    TRACERS = ["probe-fast", "rzip", "ptu"]
    data = (
        avg_times_df
        .filter(polars.col("tracer").is_in(set(TRACERS)))
        .filter(polars.col("workload").ne("torch-attention"))
        .select(
            "workload",
            "stage",
            "tracer",
            "err_overhead_%",
            "est_overhead_%",
            f"unmod_mean_{MAIN_MEASURE}",
            f"unmod_std_{MAIN_MEASURE}",
        )
        .pivot(
            on="tracer",
            index=("workload", "stage"),
            values=[
                "err_overhead_%",
                "est_overhead_%",
                f"unmod_mean_{MAIN_MEASURE}",
                f"unmod_std_{MAIN_MEASURE}",
            ],
        )
        .filter(polars.all_horizontal(polars.col("*").is_not_null()))
        .sort("workload", "stage")
        .join(
            avg_times_df
            .select("workload", "stage", f"unmod_mean_{MAIN_MEASURE}", f"unmod_std_{MAIN_MEASURE}")
            .unique(subset=("workload", "stage"), keep="first"),
            on=["workload", "stage"],
            how="inner",
        )
        .with_columns(polars.selectors.numeric().round(1))
        .sort("workload", f"unmod_mean_{MAIN_MEASURE}")
        .with_columns((polars.col("workload").ne(polars.col("workload").shift(1)) | polars.col("workload").shift(1).is_null()).alias("is_new_workload"))
    )

    print()
    print("".join([
        "".join([
            "\\midrule " + row['workload'] + " \\\\ \\midrule\n" if row["is_new_workload"] else "",
            f"{row['stage']: <20s} & ",
            rf"{row[f'unmod_mean_{MAIN_MEASURE}']:.1f} {{\tiny \(\pm\) {row[f'unmod_std_{MAIN_MEASURE}']:.1f}}} & ",
            " & ".join([
                rf"{row['est_overhead_%_' + tracer]} {{\tiny \(\pm\) {row['err_overhead_%_' + tracer]}}}"
                for tracer in TRACERS
            ]),
        ]) + " \\\\\n"
        for row in data.rows(named=True)
    ]))
    print()

    print()
    TRACERS.insert(0, "none")
    wine_tastings = (
        df
        .join(avg_times_df, how="semi", on=("workload", "stage"))
        .filter(polars.col("tracer").is_in(set(TRACERS)))
        .filter(polars.col("workload").ne("torch-attention"))
        .select(
            "workload",
            "stage",
            "tracer",
            "iteration",
            polars.col(MAIN_MEASURE) / polars.duration(seconds=1)
        )
        .filter(polars.all_horizontal(polars.col("*").is_not_null()))
        .group_by("workload", "stage", "tracer")
        .agg(polars.selectors.numeric().median())
        .pivot(
            on="tracer",
            index=("workload", "stage"),
            values=MAIN_MEASURE,
        )
        .filter(polars.all_horizontal(polars.col("*").is_not_null()))
        .pipe(lambda df: [print(df.select([col for col in df.columns if col not in TRACERS] + TRACERS)), df][1])
        .select(*TRACERS) # deterministic order
    )
    print(wine_tastings.shape)
    print(scipy.stats.friedmanchisquare(*wine_tastings.to_numpy().T))

    wine_tastings_p = wine_tastings.to_pandas()
    wine_tastings_p.columns = [
        {"probe-fast": "PROBE", "rzip": "ReproZip", "none": "native", "ptu": "PTU"}.get(column, column)
        for column in wine_tastings_p.columns
    ]
    test_results = scikit_posthocs.posthoc_conover_friedman(wine_tastings_p, p_adjust="holm")
    avg_ranks = wine_tastings_p.rank(axis=1, ascending=True).mean(axis=0)
    print(test_results)
    figure = matplotlib.figure.Figure((8.5 * 0.4, 11 * 0.2))
    ax = figure.subplots()
    scikit_posthocs.critical_difference_diagram(avg_ranks, test_results, ax=ax)
    figure.savefig("crit-diff.pdf", bbox_inches="tight")



    # for formula in [
    #         # "overhead_diff ~ 0 + tracer:count_rzip_executed_files",
    #         # "overhead_diff ~ 1 + tracer:count_rzip_executed_files",
    #         # "overhead_diff ~ 0 + tracer:count_syscalls + tracer:count_rzip_executed_files",
    #         # "overhead_diff ~ 1 + tracer:count_syscalls + tracer:count_rzip_executed_files",
    #         "overhead_diff ~ 0 + tracer:count_syscalls",
    #         # "overhead_diff ~ 1 + tracer:count_syscalls",
    #       ]:
    #     results = statsmodels.formula.api.ols(
    #         formula=formula,
    #         data=(
    #             avg_times_df
    #             .filter(polars.col("tracer").ne("none"))
    #             .filter(polars.col("overhead_diff").ge(0))
    #             .with_columns(polars.col("overhead_diff") / polars.duration(microseconds=1))
    #             .to_pandas()
    #         ),
    #     ).fit()
    #     print(f"{formula} {results.rsquared * 100:.0f}% R-squared")
    #     print(textwrap.indent(str(results.summary()), prefix="  "))
    #     print("---------")
