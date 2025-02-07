#!/usr/bin/env python
import typer
import typing
import datetime
import polars
import pandas
import itertools
import matplotlib.pyplot
import pathlib
import scipy.stats
import util
import scikit_posthocs


polars.Config.set_tbl_rows(1000)
polars.Config.set_tbl_cols(1000)


collector_order = {
    "noprov": (0,),
    "ltrace": (1,),
    "strace": (2,),
    "probe": (3,),
    "rr": (4,),
    "sciunit": (5,),
    "ptu": (6,),
    "cde": (7,),
    "reprozip": (8,),
    "care": (9,),
    "probecopyeager": (10,),
    "probecopylazy": (11,),
}


def renames(all_trials: polars.DataFrame) -> polars.DataFrame:
    workload_labels = {
        "syscall": ("syscall", "getpid"),
        "stat": ("syscall", "stat"),
        "open/close": ("syscall", "open/close"),
        "write": ("syscall", "write"),
        "read": ("syscall", "read"),
        "fork": ("syscall", "fork"),
        "exec": ("syscall", "exec"),
        "fstat": ("syscall", "fstat"),
        "shell": ("system", "launch shell"),
        "shell-cd": ("system", "shell-cd"),
        "hello": ("system", "hello-world"),
        "create/delete": ("synth. file I/O", "create/delete files"),
        "postmark2": ("synth. file I/O", "Postmark (small file I/O)"),
        "postmark": ("synth. file I/O", "Postmark (small file I/O)"),
        "titanic-0": ("data sci.", "Kaggle training/inference 2"),
        "titanic-1": ("data sci.", "Kaggle training/inference 1"),
        "house-prices-0": ("data sci.", "Kaggle training/inference 3"),
        "house-prices-1": ("data sci.", "Kaggle training/inference 4"),
        "plot-simple": ("data sci.", "Simple plot"),
        "imports": ("data sci.", "Python imports"),
        "huggingface/transformers": ("build", "Python package"),
        "apache": ("system", "Apache server load test"),
        "ph-01": ("comp. chem.", "Quantum wave fn 0"),
        "pw-01": ("comp. chem.", "Quantum wave fn 1"),
        "pp-01": ("comp. chem.", "Quantum wave fn 2"),
        "sextractor": ("build", "C pkg"),
        "blastp": ("multi-omics", "BLAST search 0"),
        "blastn": ("multi-omics", "BLAST search 1"),
        "blastx": ("multi-omics", "BLAST search 2"),
        "tblastn": ("multi-omics", "BLAST search 3"),
        "tblastx": ("multi-omics", "BLAST search 4"),
        "megablast": ("multi-omics", "BLAST search 5"),
        "umap2": ("data sci.", "Manifold learning example"),
        "umap": ("data sci.", "Manifold learning example"),
        "hdbscan": ("data sci.", "Clustering example"),
        "astro-pvd": ("comp. astro.", "Astronomical image analysis"),
        "barnes": ("comp. astro.", "N-body Barnes"),
        "fmm": ("comp. astro.", "N-body FMM"),
        "ocean": ("comp. phys.", "Ocean fluid dynamics"),
        "radiosity": ("graphics", "Radiosity"),
        "raytrace": ("graphics", "Raytracing"),
        "volrend": ("graphics", "Volume ray-casting"),
        "water-nsquared": ("comp. chem.", "Molecular dynamics 1"),
        "water-spatial": ("comp. chem.", "Molecular dynamics 2"),
        "cholesky": ("numerical", "Cholesky factorization"),
        "fft": ("numerical", "FFT"),
        "lu": ("numerical", "LU factorization"),
        "radix": ("numerical", "Radix sort"),
        "rsync-linux": ("system", "copy Linux src"),
        "tar-linux": ("system", "tar Linux src"),
        "untar-linux": ("system", "untar Linux src"),
        "1-small-hello": ("system", "tiny-hello"),
        "true": ("system", "true"),
        "ls": ("system", "ls"),
        "python noop": ("system", "python noop"),
        "small-hello": ("system", "many-tiny-hello")
    }
    workload_to_groups = {
        workload_name: group
        for workload_name, (group, _) in workload_labels.items()
    }
    workload_renames = {
        workload_name: new_workload_name
        for workload_name, (_, new_workload_name) in workload_labels.items()
    }
    unlabelled_workloads = sorted(set(all_trials["workload_subsubgroup"].unique()) - workload_labels.keys())

    if unlabelled_workloads:
        util.console.rule("Unlabelled workloads")
        util.console.print("\n".join(unlabelled_workloads))

    all_trials = all_trials.with_columns(
        polars.col("collector").cast(str).replace({"probe": "probe (metadata)", "probecopylazy": r"probe (metadata \& data)"}),
        polars.col("workload_subsubgroup").cast(str).replace(workload_renames).alias("workload"),
        polars.col("workload_subsubgroup").cast(str).replace(workload_to_groups).alias("group"),
        (polars.col("user_cpu_time") + polars.col("system_cpu_time")).alias("cpu_time")
    ).drop("workload_subgroup", "workload_subsubgroup")

    return all_trials


def remove_outliers(all_trials: polars.DataFrame) -> polars.DataFrame:
    dummy_workloads = ["failing", "tiny-hello"]
    all_trials = all_trials.filter(~polars.col("workload").is_in(dummy_workloads))

    mask = polars.col("returncode") != 0
    failures = all_trials.filter(mask)
    if not failures.is_empty():
        util.console.rule("Failures")
        util.console.print(failures.select("group", "workload", "collector"))

    all_trials = all_trials.filter(~mask)

    mask = polars.col("walltime") < datetime.timedelta(seconds=1)
    fasts = all_trials.filter(mask)
    if not fasts.is_empty():
        util.console.rule("Fast")
        util.console.print(util.dt_as_seconds(fasts.select("group", "workload", "collector", "walltime"), 3))
    all_trials = all_trials.filter(~mask)

    mask = polars.col("walltime") > 1.2 * polars.col("cpu_time")
    discrepant = all_trials.filter(mask)
    if not discrepant.is_empty():
        util.console.rule("Walltime exceeds CPU time. Did system suspend during execution?")
        util.console.print(util.dt_as_seconds(discrepant.select("group", "workload", "collector", "walltime", "cpu_time"), 3))
    all_trials = all_trials.filter(~mask)

    return all_trials


def remove_dummy_workloads(avged_trials: polars.DataFrame) -> polars.DataFrame:
    return avged_trials


def main(
        data: pathlib.Path = pathlib.Path("output/iterations.parquet"),
) -> None:
    # Typer does rich.traceback.install
    # Undo it here
    import sys
    sys.excepthook = sys.__excepthook__
    if not data.exists():
        util.console.print(f"[red]{data} does not exist!")
        raise typer.Exit(1)

    all_trials = polars.read_parquet(data)

    all_trials = renames(all_trials)

    controlled_vars = ("group" ,"workload")
    independent_vars = ("collector", "warmups")
    dependent_vars = ("walltime", "user_cpu_time", "system_cpu_time", "max_memory")

    all_trials = remove_outliers(all_trials)

    dependent_var_stats = list(util.flatten1([
        [
            *lognorm_mle(var),
            *norm_mle(var),
        ]
        for var in dependent_vars
    ]))
    avged_trials = all_trials.group_by(*independent_vars).agg(*dependent_var_stats)

    avged_trials = join_baseline(
        avged_trials,
        controlled_vars,
        independent_vars,
        ("noprov", 0),
        dependent_var_stats,
    )


def lognorm_mle(col: str) -> tuple[polars.Expr, polars.Expr]:
    return (
        polars.col(col).log().mean().alias(f"{col}_log_avg"),
        polars.col(col).log().std(ddof=1).alias(f"{col}_log_std"),
    )


def norm_mle(col: str) -> tuple[polars.Expr, polars.Expr]:
    return (
        polars.col(col).mean().alias(f"{col}_avg"),
        polars.col(col).std(ddof=1).alias(f"{col}_std"),
    )


def log_to_mean(mean: polars.Expr, std: polars.Expr) -> polars.Expr:
    return (mean + std**2 / 2).exp()


def log_to_std(mean: polars.Expr, std: polars.Expr) -> polars.Expr:
    return ((std**2).exp() - 1) * (2 * mean + std**2).exp()



def join_baseline(
        df: polars.DataFrame,
        controlled_vars: typing.Sequence[str],
        independent_vars: typing.Sequence[str],
        baseline_val_of_independent_vars: typing.Sequence[typing.Any],
        dependent_vars: typing.Sequence[polars.Expr],
) -> polars.DataFrame:
    return df.filter(
        polars.col(var) == val
        for var, val in zip(independent_vars, baseline_val_of_independent_vars)
    ).select(
        *controlled_vars,
        [
            var.alias(f"baseline_{var}")
            for var in dependent_vars
        ],
        on="workload",
        how="full",
        validate="m:1",
    )


def lognorm_ratio(numerator: str, denominator: str, result: str) -> tuple[polars.Expr, polars.Expr]:
    """Compute the log-normal distribution parameters of the ratio of two log-normal distributions

    Wise words from Wikipedia, brackets theirs:

        If two independent, log-normal variables X_1 and X_2 are multiplied [divided],
        the product [ratio] is again log-normal,
        with parameters mu=mu_1+mu_2 [mu=mu_1-mu_2]
        and sigma, where sigma^2=sigma_1^2+sigma_2^2.

    https://en.wikipedia.org/wiki/Log-normal_distribution#Multiplication_and_division_of_independent,_log-normal_random_variables
    """

    return (
        (
            polars.col(f"{numerator}_log_avg") - polars.col(f"{denominator}_log_avg")
        ).alias(f"{result}_avg"),
        (
            polars.col(f"{numerator}_log_std")**2 + polars.col(f"{denominator}_log_std")**2
        ).sqrt().alias(f"{result}_std"),
    )

def norm_ratio(numerator: str, denominator: str, result: str) -> tuple[polars.Expr, polars.Expr]:
    """Compute the ratio of means. Totally unprincipled"""

    return (
        (polars.col(f"{numerator}_avg") / polars.col(f"{denominator}_avg")).alias(f"{result}_avg"),
        (
            polars.col(f"{numerator}_avg") * polars.col(f"{denominator}_std")
            + polars.col(f"{denominator}_avg") * polars.col(f"{numerator}_std")
        ).alias(f"{result}_std"),
    )


if False:
    output = pathlib.Path(__file__).resolve().parent.parent / "docs/lib_interpos"


    def color(mean: float) -> str:
        if mean <= 1/3:
            return ""
        elif mean <= 2/3:
            return r"\cellcolor[rgb]{1, 0.8, 0.8}"
        elif mean <= 1:
            return r"\cellcolor[rgb]{1, 0.6, 0.6}"
        else:
            return r"\cellcolor[rgb]{1, 0.4, 0.4}"


    def get_one(df: polars.DataFrame, workload: str | None, collector: str | None) -> polars.DataFrame:
        if workload:
            df = df.filter(polars.col("workload") == workload)
        if collector:
            df = df.filter(polars.col("collector") == collector)
        return df


    for qty in qtys:
        util.console.rule(qty)
        util.console.print(log_normal_qtys.select(
            "group",
            "workload",
            "collector",
            polars.concat_str(
                polars.col(f"{qty}_overhead_avg2").round(1),
                polars.lit("  ±"),
                polars.coalesce(polars.col(f"{qty}_overhead_std2").round(1), polars.lit("")),
            ).alias(qty),
        ).pivot(
            "collector",
            index=("group", "workload"),
            values=qty,
        ).sort("group", "workload"))

        (output / f"data_{qty}.tex").write_text("\n".join([
                r"\begin{tabular}{ll" + "l" * len(collectors) + "}",
                r"\toprule",
                " & ".join([
                    "Group",
                    "Workload",
                    rf"\multicolumn{{{len(collectors)}}}{{c}}{{\textbf{{{qty.replace('_', ' ').capitalize()}}}}} \\",
                ]) + r" \\",
                " & ".join([
                    "",
                    "",
                    r"\multicolumn{2}{c}{Metadata-only}",
                    r"\multicolumn{3}{c}{Metadata \& data}",
                ]) + r" \\",
                " & ".join([
                    "",
                    "",
                    *collectors,
                ]) + r" \\",
                r"\midrule",
                *util.flatten1([
                    [
                        *[
                            " & ".join([
                                group,
                                workload,
                                *[
                                    (lambda mean, std: color(mean - 1) + r"\({:.0f}\%\quad \pm {:.0f}\%\)".format(mean * 100 - 100, std * 100))(
                                        get_one(log_normal_qtys, workload, collector)[0][f"{qty}_overhead_avg2"][0],
                                        get_one(log_normal_qtys, workload, collector)[0][f"{qty}_overhead_std2"][0],
                                    )
                                    if not get_one(log_normal_qtys, workload, collector).is_empty()
                                    else "-"
                                    for collector in collectors
                                ],
                            ]) + r" \\"
                            for workload in sorted(log_normal_qtys.filter(polars.col("group") == group)["workload"].unique())
                        ],
                        # " & ".join([
                        #     group,
                        #     r"\textit{avg}",
                        #     *[
                        #         (lambda mean, std: r"\({:.0f}\%\quad \pm {:.0f}\%\)".format(mean * 100 - 100, std * 100) if mean is not None else "-")(
                        #             *log_normal_qtys.filter(
                        #                 (polars.col("group") == group) & (polars.col("collector") == collector)
                        #             ).select(
                        #                 polars.col(f"{qty}_overhead_avg").mean().alias(f"{qty}_group_overhead_avg"),
                        #                 (polars.col(f"{qty}_overhead_std")**2).sum().sqrt().alias(f"{qty}_group_overhead_std"),
                        #             # ).select(
                        #             #     log_to_mean(polars.col(f"{qty}_group_log_overhead_avg"), polars.col(f"{qty}_group_log_overhead_std")),
                        #             #     log_to_std(polars.col(f"{qty}_group_log_overhead_avg"), polars.col(f"{qty}_group_log_overhead_std")),
                        #             ).rows()[0]
                        #         )
                        #         for collector in collectors
                        #     ],
                        # ]) + r" \\",
                        # r"\midrule" if not is_last else r"\bottomrule",
                    ]
                    for is_last, group in util.last_sentinel(sorted(set(workload_to_groups.values())))
                    if not log_normal_qtys.filter(
                            (polars.col("group") == group)
                    ).is_empty()
                ]),
                r"\bottomrule",
                r"\end{tabular}",
                "",
            ]))

        all_collectors = collectors
        all_workloads = list(wl for wl in iterations["workload"].unique() if wl in workload_labels)
        matrix_df = pandas.DataFrame.from_records({
            collector: [
                util.dt_as_seconds(iterations).filter(
                    (polars.col("workload") == workload) & (polars.col("collector") == collector)
                ).mean()[qty][0]
                for workload in all_workloads
            ]
            for collector in all_collectors
        }, index=all_workloads)
        p = scipy.stats.friedmanchisquare(*-matrix_df.values.T).pvalue
        util.console.print(f"P-value: {p * 100:.2f}%")
        (output / f"p_value_{qty}.tex").write_text(f"{p * 100:.2f}")
        sig_matrix = scikit_posthocs.posthoc_nemenyi_friedman(-matrix_df)
        print(sig_matrix)

        if "significant" if p < 0.05 else "inconclusive":
            print("Post-hoc:")
            # Lower is better, so we write negative sign
            significant = []
            for collector_i, collector_j in itertools.product(all_collectors, repeat=2):
                if sig_matrix.loc[collector_i, collector_j] < .05:
                    print(f"{collector_i} < {collector_j} with {sig_matrix.loc[collector_i, collector_j] * 100:.2f}%")
                    significant.append((collector_i, collector_j))

        fig = matplotlib.pyplot.figure(figsize=(10, 2), dpi=100)
        ax = fig.add_subplot(1, 1, 1)
        ax.set_title(f"Critical diff. {qty} rank of provenance tracers")
        scikit_posthocs.critical_difference_diagram(
            matrix_df.rank(axis=1, method="average").mean(axis=0),
            sig_matrix=sig_matrix,
            ax=ax
        )

        fig.savefig(output / f"ranks_{qty}.svg", bbox_inches="tight")


if __name__ == "__main__":
    with util.progress:
        typer.run(main)
