#!/usr/bin/env python
# ruff: noqa: E402
import datetime
time_start = datetime.datetime.now()
import typer
import operator
import functools
import typing
import datetime
import polars
import matplotlib.pyplot
import pathlib
import scipy.stats  # type: ignore
import util
import scikit_posthocs  # type: ignore
import numpy
import workloads

time_after_imports = datetime.datetime.now()
print(f"Time from imports {(time_after_imports - time_start).total_seconds():.1f}")


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
        "1-small-hello": ("small-calib", "1-small-hello"),
        "1-cp": ("small-calib", "1-cp"),
        "true": ("system", "true"),
        "ls": ("system", "ls"),
        "python noop": ("system", "python noop"),
        "small-hello": ("big-calib", "small-hello"),
        "failing": ("system", "failing-test"),
        "bash noop": ("system", "bash-noop"),
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
        polars.col("collector").cast(str).replace({"probe": "probe (metadata)", "probecopylazy": r"probe (metadata & data)"}),
        polars.col("workload_subsubgroup").cast(str).replace(workload_renames).alias("workload"),
        polars.col("workload_subsubgroup").cast(str).replace(workload_to_groups).alias("group"),
        (polars.col("user_cpu_time") + polars.col("system_cpu_time")).alias("cpu_time"),
    ).with_columns(
        polars.concat_str(
            polars.col("collector"),
            polars.lit(" "),
            polars.col("workload"),
        ).alias("collector_workload"),
    ).drop("workload_subgroup", "workload_subsubgroup")

    return all_trials


def remove_outliers(
        all_trials: polars.DataFrame,
        controlled_vars: typing.Sequence[str],
        independent_vars: typing.Sequence[str],
) -> polars.DataFrame:
    dummy_workloads = ["failing", "1-small-hello", "1-small-cp"]
    all_trials = all_trials.filter(~polars.col("workload").is_in(dummy_workloads))

    mask = polars.col("returncode") != 0
    failures = all_trials.filter(mask)
    if not failures.is_empty():
        util.console.rule(f"Failures {len(failures)}")
        util.console.print(
            all_trials
            .group_by("group", "workload", "collector")
            .agg((100 * (polars.col("returncode") == 0).sum() / polars.len()).alias("failure_prec"))
            .filter(polars.col("failure_prec") > 0)
            .sort("failure_prec", descending=True)
            .select("group", "workload", "collector", polars.col("failure_prec").round(0))
            .head(20)
        )

    all_trials = all_trials.filter(~mask)

    mask = polars.col("walltime") < datetime.timedelta(seconds=1)
    fasts = all_trials.filter(mask)
    if not fasts.is_empty():
        util.console.rule(f"Fast {len(fasts)}")
        util.console.print(
            util.dt_as_seconds(fasts.select("group", "workload", "walltime"), 3)
            .group_by("group", "workload")
            .min()
            .head(20)
        )
    all_trials = all_trials.filter(~mask)

    max_count = list((
        all_trials
        .group_by(*controlled_vars, *independent_vars)
        .agg(polars.len().alias("count"))
        .max()
    )["count"])[0]
    missing = (
        all_trials
        .group_by(*controlled_vars, *independent_vars)
        .agg(polars.len().alias("count"))
        .filter(polars.col("count") < max_count)
    )
    if not missing.is_empty():
        util.console.rule(f"Missing values {len(missing)}")
        util.console.print(missing.head(20))

    return all_trials


def verify_assumptions(all_trials: polars.DataFrame, output: pathlib.Path) -> None:
    qty = "walltime"
    small_calib_runs = (
        all_trials
        .filter(polars.col("group") == "small-calib")
        .select("collector_workload", "collector", "workload", "n_warmups", qty)
        # .with_columns(
        #     polars.concat_str(
        #         polars.col("iteration"),
        #         polars.lit(" "),
        #         polars.col("collector_workload")
        #     ).alias("iteration_collector_workload")
        # )
        .pipe(
            lambda small_calib_runs:
            small_calib_runs
            .join(
                small_calib_runs.group_by("collector_workload").agg(polars.mean(qty).alias(f"{qty}_cw_mean")),
                on="collector_workload",
                how="full",
                validate="m:1",
            )
            .with_columns((polars.col(qty) / polars.col(f"{qty}_cw_mean")).alias(f"{qty}_cw_z"))
            .join(
                small_calib_runs.group_by("workload").agg(polars.mean(qty).alias(f"{qty}_w_mean")),
                on="workload",
                how="full",
                validate="m:1",
            )
            .with_columns((polars.col(qty) / polars.col(f"{qty}_w_mean")).alias(f"{qty}_w_z"))
            .with_columns(polars.col(f"{qty}_w_z").log().alias(f"{qty}_w_z_log"))
        )
    )
    n_warmups_ignored: int | None = None
    for collector_workload in small_calib_runs.unique("collector_workload")["collector_workload"]:
        tmp = numpy.abs(
            numpy.diff(
                small_calib_runs
                .filter(polars.col("collector_workload") == collector_workload)
                .sort("n_warmups")
                ["walltime"]
                .dt.total_microseconds()
                .to_numpy()
            )
        )
        # penalize choosing a later cutoff, unless the diff is overwhelming
        tmp = tmp / (numpy.arange(len(tmp)) + 1)**(1/3)
        if len(tmp):
            n_warmups_ignored = min(n_warmups_ignored, tmp.argmax()) if n_warmups_ignored is not None else tmp.argmax()
    assert n_warmups_ignored is not None
    print(f"Algorithm wants to ignore {n_warmups_ignored}")
    n_warmups_ignored = 1
    output = output / "small-calib-lines.svg"
    print(f"Verify that the results are the same after {n_warmups_ignored} for all collectors (lines) in {output}")
    fig = matplotlib.figure.Figure()
    ax = fig.add_subplot(1, 1, 1)
    lines(
        ax,
        small_calib_runs,
        "n_warmups",
        f"{qty}_cw_z",
        "collector_workload",
    )
    ax.set_xlabel("walltime / mean")
    ax.set_ylabel("Z-score")
    ymin, ymax = ax.get_ylim()
    ax.plot(
        (n_warmups_ignored, n_warmups_ignored),
        (ymin, ymax),
        linestyle="--",
        color="gray",
        label="Ignored workloads",
    )
    ax.set_ylim(ymin, ymax)
    ax.set_xlim(0, n_warmups_ignored * 6)
    ax.set_xticks(range(0, n_warmups_ignored * 6))
    fig.savefig(output, bbox_inches="tight")

    for workload in small_calib_runs.unique("workload")["workload"]:
        df = small_calib_runs.filter(polars.col("workload") == workload)
        total_mean = (
            df
            ["walltime"]
            .dt.total_microseconds()
            .to_numpy()
            [n_warmups_ignored:]
            .mean()
        )
        collectors = sorted(small_calib_runs["collector"].unique())
        data = [
            (
                df
                .filter(polars.col("collector") == collector)
                ["walltime"]
                .dt.total_microseconds()
                .to_numpy()
            )
            for collector in collectors
        ]
        normed_stddevs = numpy.array([
            row.std(ddof=1) / total_mean
            for row in data
        ])
        assert normed_stddevs.shape[0] == len(collectors)
        for i, (collector, stddev) in enumerate(sorted(zip(collectors, normed_stddevs), key=lambda pair: pair[1])):
            print(f"{collector: <30s}: {normed_stddevs[i]:.2f}")
        max_diff = normed_stddevs.max() - normed_stddevs.min()
        print(f"Max diff: {max_diff:.2f} from {collectors[normed_stddevs.argmax()]} to {collectors[normed_stddevs.argmin()]}")
        if max_diff > 0.1:
            print("Doesn't seem homoscedastic")
        else:
            print("Seems homoscedastic")

        print(f"Levene's test for homoscedastic (small means not homoscedastic): {scipy.stats.levene(*data).pvalue:.1e}")

        output = output / f"small-calib-histograms-{workload}.svg"
        print(f"Verify normality (symmetric bell) and heterscedasticity (same width) in {output}")
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        histogram(
            ax,
            df,
            f"{qty}_w_z",
            "collector",
            cap=5
        )
        ax.set_xlim(0, 4)
        fig.legend()
        fig.savefig(output, bbox_inches="tight")
        output = output / f"small-calib-qq-{workload}.svg"
        print(f"Verify normality (linear) and homoscedasticity (same slope) in {output}")
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        qq_plot(
            ax,
            df,
            f"{qty}_w_z",
            "collector",
        )
        fig.legend()
        fig.savefig(output, bbox_inches="tight")

        output = output / f"small-calib-histograms-{workload}-log.svg"
        print(f"Verify normality (symmetric bell) and heterscedasticity (same width) in {output}")
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        qq_plot(
            ax,
            df,
            f"{qty}_w_z_log",
            "collector",
        )
        fig.legend()
        fig.savefig(output, bbox_inches="tight")
        for i, collector in enumerate(df.unique("collector").sort("collector")["collector"]):
            population = df.filter(polars.col("collector") == collector)["walltime"].to_numpy().astype(numpy.float128)
            p_value = scipy.stats.shapiro(population)[1]
            p_value2 = scipy.stats.shapiro(numpy.log(population))[1]
            p_value3 = scipy.stats.shapiro(numpy.log(numpy.log(population)))[1]
            print(f"P-value {collector} {workload} is normal = {p_value:.1e}, log-normal = {p_value2:.1e}, loglog-normal = {p_value3:.1e}")


def calibrate_errors(all_trials: polars.DataFrame) -> None:
    qty = "walltime"
    small_calib_runs = (
        all_trials
        .filter(polars.col("group") == "small-calib")
        .select("collector_workload", "collector", "workload", "n_warmups", qty)
    )
    big_calib_runs = (
        all_trials
        .filter(polars.col("group") == "big-calib")
        .select("collector_workload", "collector", "workload", "n_warmups", qty)
    )
    one_run = small_calib_runs.filter(
        (polars.col("workload") == "1-small-hello") &
        (polars.col("collector") == "noprov")
    )["walltime"].dt.total_microseconds().to_numpy().astype(numpy.float128)
    many_run = big_calib_runs.filter(
        (polars.col("workload") == "small-hello") &
        (polars.col("collector") == "noprov")
    )["walltime"].dt.total_microseconds().to_numpy().astype(numpy.float128)
    # one_run                = benchmark_overhead + true_run_time
    # many_run               = benchmarK_overhead + C * true_run_time
    # C * one_run - many_run = (C - 1) * benchmark_overhead
    benchmark_overhead = (workloads.calibration_ratio * one_run.mean() - many_run.mean()) / (workloads.calibration_ratio - 1)
    print(f"Overhead = {benchmark_overhead:.0f}us")

    # X_observed ~ X_true + abs_noise + prop_noise * X_true
    # where X_true is a real, abs_noise and prop_noise are centered random variables
    # Var(X_observed) = 0 + Var(abs_noise) + Var(prop_noise) * X_true^2
    # Var(one_run) = abs_noise + prop_noise*one_run_mean^2
    # Var(many_run) = abs_noise + prop_noise*many_run_mean^2

    # Var(one_run) - Var(many_run) = prop_noise*(one_run_mean^2 - many_run_mean^2)
    prop_noise = (numpy.var(many_run) - numpy.var(one_run)) / (many_run.mean()**2 - one_run.mean()**2)
    print(f"Relative noise = {numpy.sqrt(prop_noise):.3f}")

    # many_run_mean^2*Var(one_run) - one_run_mean^2*Var(many_run) = (many_run_mean^2 - one_run_mean^2)*abs_noise
    noise = (many_run.mean()**2 * numpy.var(one_run) - one_run.mean()**2 * numpy.var(many_run)) / (many_run.mean()**2 - one_run.mean()**2)
    print(f"Absolute noise (stddev) = {numpy.sqrt(noise):.2f}us")

def show_collector_workload_matrix(
        all_trials: polars.DataFrame,
        n_warmups_ignored: int,
        output: pathlib.Path,
) -> None:
    controlled_vars = ("workload",)
    independent_vars = ("collector",)
    dependent_vars = ("walltime", "user_cpu_time", "system_cpu_time", "max_memory")

    dependent_var_stats = [
        *util.flatten1([
            [
                *lognorm_mle(var),
                *norm_mle(var),
            ]
            for var in dependent_vars
        ]),
        polars.len().alias("count"),
    ]
    dependent_var_stats_names = [
        var.meta.output_name()
        for var in dependent_var_stats
    ]

    avged_trials = (
        all_trials
        .group_by(*controlled_vars, *independent_vars)
        .agg(*dependent_var_stats)
        .pipe(lambda avged_trials: join_baseline(
            avged_trials,
            controlled_vars,
            independent_vars,
            ("noprov", 0),
            dependent_var_stats_names,
        ))
        .with_columns(*util.flatten1([
            lognorm_ratio(var, f"baseline_{var}", f"ratio_{var}")
            for var in dependent_vars
        ]))
    )
    collectors = list(avged_trials.unique("collector").sort("collector")["collector"])
    workloads = list(avged_trials.unique("workload").sort("workload")["workload"])
    for var in dependent_vars:
        collectors = sorted(
            collectors,
            key=lambda collector: avged_trials.filter(polars.col("collector") == collector)[f"ratio_{var}_avg"].to_numpy().mean(),
        )
        workloads = sorted(
            workloads,
            key=lambda workload: avged_trials.filter(polars.col("workload") == workload)[f"ratio_{var}_avg"].to_numpy().mean(),
        )
        fig = matplotlib.figure.Figure(figsize=(len(workloads) * 2, len(collectors) * 2))
        ax = fig.add_subplot(1, 1, 1)
        im = ax.imshow(
            avged_trials
            .pivot(
                on="collector",
                index="workload",
                values=f"ratio_{var}_avg",
            )
            .select(collectors)
            .to_numpy(),
        )
        ax.set_xticks(range(len(collectors)), collectors, rotation=90)
        ax.set_yticks(range(len(workloads)), workloads)
        fig.colorbar(im)
        text = (
            avged_trials
            .with_columns(
                polars.concat_str(
                    ((polars.col(f"ratio_{var}_avg").exp() - 1.0) * 100).round(0).cast(int),
                    # polars.lit(" ±"),
                    # polars.col(f"ratio_{var}_std").exp().round(0).astype(int),
                ).alias(f"ratio_{var}_text")
            )
            .pivot(
                on="collector",
                index="workload",
                values=f"ratio_{var}_text",
            )
            .select(collectors)
            .to_numpy()
        )
        for i, collector in enumerate(collectors):
            for j, workload in enumerate(workloads):
                ax.text(i, j, text[j, i], ha="center", va="center", color="white", fontsize=10)
        fig.savefig(output / f"matrix_{var}.svg", bbox_inches="tight")


def main(
        data: pathlib.Path = pathlib.Path("output/iterations.parquet"),
        output: pathlib.Path = pathlib.Path("output"),
) -> None:
    # Typer does rich.traceback.install
    # Undo it here
    import sys
    sys.excepthook = sys.__excepthook__
    if not data.exists():
        util.console.print(f"[red]{data} does not exist!")
        raise typer.Exit(1)

    time_main_start = datetime.datetime.now()
    print(f"Time main starts {(time_main_start - time_after_imports).total_seconds():.1f}")

    all_trials = polars.read_parquet(data)

    all_trials = renames(all_trials)

    controlled_vars = ("group" ,"workload")
    independent_vars = ("collector", "n_warmups")
    dependent_vars = ("walltime", "user_cpu_time", "system_cpu_time", "max_memory")

    verify_assumptions(all_trials, output)

    calibrate_errors(all_trials)

    all_trials = remove_outliers(all_trials, controlled_vars, independent_vars)

    time_main_substance = datetime.datetime.now()
    print(f"Time substance done {(time_main_substance - time_main_start).total_seconds():.1f}")


    # anova(
    #     all_trials
    #     .pivot(
    #         "collector",
    #         index=("group", "workload", "n_warmups"),
    #         values="walltime",
    #     )
    #     .sort("group", "workload", "n_warmups")
    # )

    show_collector_workload_matrix(
        all_trials,
        n_warmups_ignored=1,
        output=output,
    )

    dependent_var_stats = [
        *util.flatten1([
            [
                *lognorm_mle(var),
                *norm_mle(var),
            ]
            for var in dependent_vars
        ]),
        polars.len().alias("count"),
    ]
    dependent_var_stats_names = [
        var.meta.output_name()
        for var in dependent_var_stats
    ]

    avged_trials = all_trials.group_by(*controlled_vars, *independent_vars).agg(*dependent_var_stats)

    avged_trials = join_baseline(
        avged_trials,
        controlled_vars,
        independent_vars,
        ("noprov", 0),
        dependent_var_stats_names,
    )

    avged_trials.write_parquet(data.parent / "avged_trials.parquet")

    time_main_done = datetime.datetime.now()
    print(f"Time main done {(time_main_done - time_main_substance).total_seconds():.1f}")


def lines(
        ax: matplotlib.axes.Axes,
        df: polars.DataFrame,
        continuous_var: str,
        dependent_var: str,
        categorical_var: str,
        legend: bool = True,
) -> None:
    for category in df.unique(categorical_var).sort(categorical_var)[categorical_var]:
        sub_df = df.filter(polars.col(categorical_var) == category).sort(continuous_var)
        ax.plot(
            sub_df[continuous_var].to_numpy(),
            sub_df[dependent_var].to_numpy(),
            label=category,
        )


def histogram(
        ax: matplotlib.axes.Axes,
        df: polars.DataFrame,
        population_var: str,
        categorical_var: str,
        cap: float,
) -> None:
    max = typing.cast(float | int, df[population_var].max())
    for i, category in enumerate(df.unique(categorical_var).sort(categorical_var)[categorical_var]):
        population = df.filter(polars.col(categorical_var) == category)[population_var].to_numpy()
        kde = scipy.stats.gaussian_kde(population)
        ts = numpy.linspace(0, max, int(max * 30))
        ax.plot(
            ts,
            numpy.clip(kde(ts), 0, cap),
            label=category,
            color=colors(i),
        )


def qq_plot(
        ax: matplotlib.axes.Axes,
        df: polars.DataFrame,
        population_var: str,
        categorical_var: str,
) -> None:
    for i, category in enumerate(sorted(df.unique(categorical_var).sort(categorical_var)[categorical_var])):
        population = df.filter(polars.col(categorical_var) == category)[population_var].to_numpy()
        population = (population - population.mean()) / population.std()
        (osm, osr), (slope, intercept, r) = scipy.stats.probplot(population, dist="norm", fit=True, plot=None)
        ax.plot(osm, osr, label=category, color=colors(i))


cmap = matplotlib.cm.tab20.colors  # type: ignore
def colors(i: int) -> typing.Any:
    return cmap[i % len(cmap)]


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
        dependent_vars: typing.Sequence[str],
) -> polars.DataFrame:
    return df.join(
        df.filter(functools.reduce(operator.and_, [
            polars.col(var) == val
            for var, val in zip(independent_vars, baseline_val_of_independent_vars)
        ])).select(
            *controlled_vars,
            *[
                polars.col(var).alias(f"baseline_{var}")
                for var in dependent_vars
            ],
        ),
        on=controlled_vars,
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


def is_different(
        df: polars.DataFrame,
        controlled_vars: list[str],
        independent_vars: list[str],
        dependent_vars: list[str],
        normal: bool,
        homoscedastic: bool,
) -> None:
    # has_replicants = df.group_by(*controlled_vars, *independent_vars).agg(polars.len().alias("count")).min() >= 2
    n_factors = len(independent_vars)
    n_treatments = df.n_unique(*independent_vars)
    numpy_df = df.to_numpy()
    assert len(numpy_df) == n_treatments
    if n_factors == 1 and normal and homoscedastic:
        if n_treatments == 1:
            result = scipy.stats.ttest_ind(numpy_df[0], numpy_df[1])
            result.statistic
            result.pvalue
            scikit_posthocs.posthoc_tukey(df)
        if n_treatments > 1:
            numpy_df = df.to_numpy()
            assert len(numpy_df) == n_treatments
            result = scipy.stats.f_oneway(*numpy_df)
            result.statistic
            result.pvalue
            scikit_posthocs.posthoc_tukey(df)


if __name__ == "__main__":
    with util.progress:
        typer.run(main)
