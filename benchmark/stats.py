import pathlib
import pandas
import numpy
import functools
import collections
import operator
import hashlib
import charmonium.time_block
from typing import Mapping, Callable
from util import flatten1
from prov_collectors import PROV_COLLECTORS
from workloads import WORKLOADS


rel_qois = ["cputime", "walltime", "memory"]
abs_qois = ["storage", "n_ops"]
output = pathlib.Path("output")
output.mkdir(exist_ok=True)


@charmonium.time_block.decor()
def output_features(df: pandas.DataFrame) -> None:
    agged = (
        df
        .groupby(["collector", "workload"], observed=True, as_index=True)
        .agg(**{
            **{
                f"{qoi}_std": pandas.NamedAgg(qoi, "std")
                for qoi in abs_qois + rel_qois
            },
            **{
                f"{qoi}_mean": pandas.NamedAgg(qoi, "mean")
                for qoi in abs_qois + rel_qois
            },
            "op_type_counts_sum": pandas.NamedAgg(
                "op_type_counts",
                lambda op_type_counts: functools.reduce(operator.add, op_type_counts, collections.Counter()),
            ),
            "count": pandas.NamedAgg("walltime", lambda walltimes: len(walltimes)),
            "workload_kind": pandas.NamedAgg(
                "workload_kind",
                "last",
            ),
        })
        .assign(**{
            "rel_slowdown": lambda df: df["walltime_mean"] / df.loc["noprov"]["walltime_mean"],
            "slowdown_diff": lambda df: df.loc["noprov"]["walltime_mean"] - df["walltime_mean"],
        })
        .assign(**{
            "log_rel_slowdown": lambda df: numpy.log(df["rel_slowdown"]),
        })
    )
    agged.to_pickle(output / "agged.pkl")

    collectors = df["collector"].unique()
    if "probe" in collectors and "noprov" in collectors:
        noprov = agged.loc["noprov"]
        probe = agged.loc["probe"]
        all_libcalls = collections.Counter[str]()
        for counter in probe["op_type_counts"]:
            all_libcalls += counter
        features_df = pandas.DataFrame({
            libcall_group + "_libcalls": probe["op_type_counts_sum"][libcall_group]
            for libcall_group in all_libcalls.keys()
            # TODO: Total syscalls.
        })
        features_df.to_pickle(output / "features_df.pkl")

        tmp_df = agged.reset_index().pivot(index="collector", columns="workload", values="log_rel_slowdown")

        assert all(
            workload0 == workload1
            for workload0, workload1 in zip(tmp_df.columns, features_df.index)
        )

        numpy.save(output / "systems_by_benchmarks", tmp_df.values)
        numpy.save(output / "benchmarks_by_features", features_df.values)
        (output / "systems.txt").write_text("\n".join(agged.index.levels[0]))
        (output / "benchmarks.txt").write_text("\n".join(agged.index.levels[1]))
        (output / "features.txt").write_text("\n".join(features_df.columns))

@charmonium.time_block.decor()
def performance(df: pandas.DataFrame) -> None:
    mean_df = (
        df
        .groupby(["workload", "collector"], as_index=True, observed=True)
        .agg(**{
            qoi + "_abs_mean": pandas.NamedAgg(
                column=qoi,
                aggfunc="mean",
            )
            for qoi in rel_qois + abs_qois
        })
    )
    with (output / "performance.txt").open("w") as output_file:
        print(
            mean_df
            .drop(["cputime_abs_mean", "memory_abs_mean"], axis=1)
            .rename(columns={
                "walltime_abs_mean": "Walltime (sec)",
                # "memory_abs_mean": "Memory (MiB)",
                "storage_abs_mean": "Storage (MiB)",
                "n_ops_abs_mean": "Prov Ops (K Ops)",
                # "n_unique_files_abs_mean": "Unique files",
            }).to_string(formatters={
                "Walltime (sec)": lambda val: f"{val:.1f}",
                "Memory (MiB)": lambda val: f"{val / 1024**2:.1f}",
                "Storage (MiB)": lambda val: f"{val / 1024**2:.1f}",
                "Prov Ops (K Ops)": lambda val: f"{val / 1e3:.1f}",
                # "Unique files": lambda val: f"{val:.0f}",
            }),
            file=output_file
        )
        total = mean_df.loc[:, "walltime_abs_mean"].sum()
        print(f"Noprov total {total:.0f}s", file=output_file)


@charmonium.time_block.decor()
def op_freqs(df: pandas.DataFrame) -> None:
    print((
        df
        .drop(["workload", "collector_method", "collector_submethod", "workload_kind"] + rel_qois + abs_qois, axis=1)
        .groupby("collector", observed=True)
        .agg(**{
            "op_count_pairs": pandas.NamedAgg(
                column="operations",
                aggfunc=lambda opss: collections.Counter(op.type for ops in opss for op in ops).most_common(),
            ),
        })
        .explode("op_count_pairs")
        .loc[lambda df: ~pandas.isna(df.op_count_pairs)]
        .assign(**{
            "op_type"  : lambda df: [pair[0] for pair in df.op_count_pairs],
            "op_counts": lambda df: [pair[1] for pair in df.op_count_pairs],
        })
        .drop(["op_count_pairs"], axis=1)
    ).to_string())


@charmonium.time_block.decor()
def relative(df: pandas.DataFrame):
    import matplotlib.figure

    @functools.cache
    def _workload_baseline(workload: str, qoi: str) -> float:
        return numpy.median(
            df[(df["workload"] == workload) & (df["collector"] == "noprov")][qoi]
        )

    with (output / "relative.txt").open("w") as output_file:
        print("len df:", len(df), file=output_file)
        for qoi in ["walltime"]:
            collectors = sorted(
                df.collector.cat.categories,
                key=lambda collector: numpy.mean([
                    df[(df["workload"] == workload) & (df["collector"] == collector)][qoi]
                    for workload in df.workload.cat.categories
                ])
            )
            print(qoi, file=output_file)
            print("Collectors:")
            for collector in collectors:
                print(f"{collector:10s}", end=" ", file=output_file)
                for rank in [5, 50, 95]:
                    value = numpy.mean([
                        numpy.percentile(
                            df[(df["workload"] == workload) & (df["collector"] == collector)][qoi],
                            rank,
                        ) / _workload_baseline(workload, qoi)
                        for workload in df.workload.cat.categories
                    ])
                    print(f"{value:4.2f}", end=" ", file=output_file)
                print(file=output_file)
            print()
            print("Workloads/Collectors:")
            for workload in df.workload.cat.categories:
                print(f"{workload}", end="\n", file=output_file)
                for collector in collectors:
                    print(f"{' ':10s} {collector:10s}", end=" ", file=output_file)
                    for rank in [5, 50, 95]:
                        value = numpy.mean([
                            numpy.percentile(
                                df[(df["workload"] == workload) & (df["collector"] == collector)][qoi],
                                rank,
                            ) / _workload_baseline(workload, qoi)
                        ])
                    print(f"{value:4.2f}", end=" ", file=output_file)
                    print(file=output_file)

    fig = matplotlib.figure.Figure()
    ax = fig.add_subplot(1, 1, 1)
    mat = numpy.array([
        list(flatten1(
            sorted(df[(df["workload"] == workload) & (df["collector"] == collector)]["walltime"] / _workload_baseline(workload, "walltime"))
            for collector in collectors
        ))
        for workload in df.workload.cat.categories
    ])
    ax.matshow(mat, vmin=numpy.log(1), vmax=numpy.log(12))
    n_samples = len(df) // len(df.workload.cat.categories) // len(df.collector.cat.categories)
    ax.set_xticks(
        ticks=range(0, len(collectors) * n_samples, n_samples),
        labels=[f"{collector}" for collector in collectors],
        rotation=90,
    )
    ax.set_yticks(
        ticks=range(len(df.workload.cat.categories)),
        labels=[
            workload
            for workload in df.workload.cat.categories
        ],
    )
    fig.savefig(output / "relative.png")


@charmonium.time_block.decor()
def minimize(df: pandas.DataFrame):
    import matplotlib.figure
    import matplotlib.colors
    import matplotlib.cm
    import matplotlib.lines
    import scipy.linalg
    import scipy.linalg.interpolative

    mean_df = (
        df
        .groupby(["workload", "collector"], as_index=True, observed=True)
        .agg(**{
            "walltime_abs_mean": pandas.NamedAgg(
                column="walltime",
                aggfunc="mean",
            )
        })
        .reset_index()
        .pivot(index="collector", columns="workload", values="walltime_abs_mean")
    )
    workloads = list(mean_df.columns)
    synthetic_features = numpy.array([
        [
            df[(df["collector"] == "fsatrace") & (df["workload"] == workload)]["n_ops"].mean()
            for workload in workloads
        ],
        # [
        #     df[(df["collector"] == "noprov") & (df["workload"] == workload)]["cputime"].mean()
        #     for workload in workloads
        # ],
    ]) / numpy.array([
        df[(df["collector"] == "noprov") & (df["workload"] == workload)]["walltime"].mean()
        for workload in workloads
    ])
    collectors = list(mean_df.index) + ["ops/sec"]
    data = numpy.vstack([mean_df.to_numpy(), synthetic_features])
    collectors_proj, singular_values, workloads_proj = scipy.linalg.svd(data)
    workload_to_kind = {
        workload.name: workload.kind
        for workload in WORKLOADS
    }
    kind_to_color = dict(zip(
        sorted(list(set(workload.kind for workload in WORKLOADS))),
        sorted(matplotlib.cm.Dark2.colors + matplotlib.cm.Set2.colors),
    ))
    (output / "sing_val").write_text("Singular values:\n" + "\n".join([f"{i: >3d}: {x:.1f}" for i, x in enumerate(singular_values)]) + "\n")
    def report_id(k: int) -> None:
        with (output / f"minimize_to_{k}_summary.txt").open("w") as output_file:
            print(f"Using {k}", file=output_file)
            idx, proj = scipy.linalg.interpolative.interp_decomp(data, k, rand=False)
            print("Interpolative decomposition chose:", ", ".join([workloads[i] for i in idx[:k]]), file=output_file)
            print("proj:", numpy.array_repr(proj), file=output_file)
            skel = scipy.linalg.interpolative.reconstruct_skel_matrix(data, k, idx)
            data_est = scipy.linalg.interpolative.reconstruct_matrix_from_id(skel, idx, proj)
            for j, workload in enumerate(workloads):
                mean_rel_error = numpy.sum(numpy.fabs((data_est[:, j] - data[:, j]) / data[:, j])) / len(collectors)
                print(f"{workload:<15s} {mean_rel_error*100:.1f}% {'by defn' if j in idx[:k] else ''}", file=output_file)
            for i, collector in enumerate(collectors):
                mean_rel_error = numpy.sum(numpy.fabs((data_est[i, :] - data[i, :]) / data[i, :])) / len(collectors)
                print(f"{collector:<15s} {mean_rel_error*100:.1f}%", file=output_file)
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        colors = numpy.array([
            kind_to_color[workload_to_kind[workload]]
            for workload in workloads
        ])
        for j in range(len(workloads)):
            ax.plot(workloads_proj[j, 0], workloads_proj[j, 1], linestyle="", marker=".", color=colors[j])
        for j in idx[:k]:
            ax.plot(workloads_proj[j, 0], workloads_proj[j, 1], linestyle="", marker="x", color=colors[j])
        ax.legend(
            handles=[
                *[
                    matplotlib.lines.Line2D([0], [0], color=color, linestyle="", marker=".", label=kind)
                    for kind, color in kind_to_color.items()
                ],
                matplotlib.lines.Line2D([0], [0], color="black", linestyle="", marker="x", label="chosen")
            ],
            bbox_to_anchor=(1.04, 0.5),
            loc="center left",
            borderaxespad=0,
        )
        fig.savefig(output / f"minimize_to_{k}_pca.png", bbox_inches="tight")
    for k in range(1, min(len(workloads), len(collectors)) + 1):
        report_id(k)


@charmonium.time_block.decor()
def mle_model(df: pandas.DataFrame) -> None:
    mean_df = (
        df
        .groupby(["workload", "collector"], as_index=True, observed=True)
        .agg(**{
            qoi + "_abs_mean": pandas.NamedAgg(
                column=qoi,
                aggfunc="mean",
            )
            for qoi in rel_qois + abs_qois
        })
    )
    workload_syscalls = [
        numpy.mean(df[(df["workload"] == workload) & (df["collector"] == "strace")]["n_ops"])
        for workload in df.workload.cat.categories
    ]

@charmonium.time_block.decor()
def bayesian(df: pandas.DataFrame) -> None:
    import pymc  # type: ignore
    import arviz
    import matplotlib.figure

    random_seed = 0
    cache = pathlib.Path(".cache")
    quality = 0
    coords = {
        "data": df.index,
        "workload": df.workload.cat.categories,
        "collector": df.collector.cat.categories,
    }
    with charmonium.time_block.ctx("model"), pymc.Model(coords=coords) as model:
        workload_idx = pymc.ConstantData(
            "workload_idx",
            df.workload.cat.codes,
            dims="data",
        )
        collector_idx = pymc.ConstantData(
            "collector_idx",
            df.collector.cat.codes,
            dims="data",
        )
        # TODO: rewrite in terms of collector_idx
        is_baseline = df.collector.cat.categories == "noprov"
        workload_runtime = pymc.Exponential(
            "workload_runtime",
            1/10,
            dims="workload",
        )
        workload_syscalls = pymc.ConstantData(
            "workload_syscalls",
            [
                numpy.mean(df[(df["workload"] == workload) & (df["collector"] == "strace")]["n_ops"])
                for workload in df.workload.cat.categories
            ],
            dims="workload",
        )
        workload_syscalls_per_second = pymc.Deterministic(
            "workload_syscalls_per_second",
            workload_syscalls / workload_runtime,
            dims="workload",
        )
        collector_runtime_per_syscall = pymc.math.switch(
            is_baseline,
            0,
            pymc.Exponential(
                "collector_runtime_per_syscall",
                1/1e-3,
                dims="collector",
            ),
        )
        workload_collector_runtime = pymc.Deterministic(
            "workload_collector_runtime",
            workload_runtime[:, numpy.newaxis] + workload_syscalls[:, numpy.newaxis] * collector_runtime_per_syscall[numpy.newaxis, :],
            dims=("workload", "collector"),
        )
        workload_collector_overhead = pymc.Deterministic(
            "workload_collector_overhead",
            workload_collector_runtime / workload_runtime[:, numpy.newaxis],
            dims=("workload", "collector"),
        )
        runtime_stddev = pymc.Exponential("runtime_stddev", 1/1, dims="workload")
        runtime = pymc.Normal(
            "runtime",
            mu=workload_collector_runtime[workload_idx, collector_idx],
            sigma=runtime_stddev[workload_idx],
            observed=df.walltime,
            dims="data",
        )

    with charmonium.time_block.ctx("Graphing model"):
        graph = pymc.model_to_graphviz(model)
        graph.render(outfile="output/bayesian_model.png")
        pathlib.Path("output/bayesian_model.dot").write_text(graph.source)
        graph_str = hashlib.sha256("\n".join(sorted(graph.source.split("\n"))).encode()).hexdigest()[:10]
        print("model:", graph_str)

    with charmonium.time_block.ctx("Prior predictive"):
        priors = pymc.sample_prior_predictive(
            random_seed=random_seed,
            model=model,
        )

    with charmonium.time_block.ctx("Plot prior predictive"):
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        arviz.plot_forest(priors.prior.workload_runtime, ax=ax)
        fig.savefig(output / "bayesian_prior_predictive_all.png")

        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.bar(df.workload.cat.categories, priors.constant_data.workload_syscalls)
        fig.savefig(output / "workload_syscalls.png")

        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        arviz.plot_forest(priors.constant_data.workload_syscalls * priors.prior.collector_runtime_per_syscall, ax=ax)
        fig.savefig(output / "bayesian_prior_predictive_runtime.png")

        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot(1, 1, 1)
        arviz.plot_forest(priors.prior.workload_collector_overhead, ax=ax)
        if ax.get_xlim()[1] > 10:
            ax.set_xlim(1, 10)

    with charmonium.time_block.ctx("MCMC"):
        cache_file = cache / f"trace-{graph_str}.hdf5"
        if cache_file.exists():
            trace = arviz.from_netcdf(cache_file)  # type: ignore
        else:
            with model:
                trace = pymc.sample(
                    random_seed=random_seed,
                    progressbar=True,
                    tune={0: 100, 1: 500, 2: 1000}[quality],
                    draws={0: 100, 1: 500, 2: 1000}[quality],
                    chains={0: 1, 1: 2, 2: 4}[quality],
                )
                trace.to_netcdf(cache_file)  # type: ignore

                # check convergence diagnostics
                assert all(arviz.rhat(trace) < 1.03)  # type: ignore

    with charmonium.time_block.ctx("Plot MCMC"):
        axes = arviz.plot_trace(
            trace,
            figsize=(12, 4 * len(trace.posterior))
        )
        fig = axes.flatten().figure
        fig.savefig(output / "mcmc_trace.png")

        def ident(x):
            return x

        exclude_baseline = {
            "collector": [
                category
                for category in df.collector.cat.categories
                if category not in {"noprov"}
            ],
        }
        variables = [
            ("workload_runtime", "sec", ident, None),
            #("workload_syscalls", "#", ident, None),
            ("workload_syscalls_per_second", "K calls / sec", lambda x: x / 1e3, None),
            ("collector_runtime_per_syscall", "log 10 sec", numpy.log10, exclude_baseline),
            ("workload_collector_runtime", "sec", ident, None),
            ("workload_collector_overhead", "overhead (prov ÷ no prov)", ident, None),
            ("runtime_stddev", "sec", ident, None),
        ]

        for variable, label, transform, coords in variables:
            axes = arviz.plot_forest(
                trace,
                var_names=[variable],
                transform=transform,
                coords=coords,
                combined=True,
            ).ravel()
            axes[0].set_title(variable)
            axes[0].set_xlabel(label)
            figure = axes[0].figure
            figure.savefig(
                f"output/bayesian_posterior_forest_{variable}.png",
                bbox_inches="tight",
            )

        fig = matplotlib.pyplot.figure()
        ax = fig.add_subplot(1, 1, 1)
        n_points = 30
        for workload_idx, workload in enumerate(df.workload.cat.categories):
            ax.plot(
                trace.posterior.workload_runtime.isel(workload=workload_idx, draw=range(n_points)).data.flatten(),
                [trace.constant_data.workload_syscalls.isel(workload=workload_idx)] * n_points * trace.posterior.dims["chain"],
                label=workload,
                marker=".",
                linestyle="",
            )
        ax.set_xlim(0, ax.get_xlim()[1])
        ax.set_ylim(0, ax.get_ylim()[1])
        xs = numpy.array(ax.get_xlim())
        for rate in ["1e4", "1e3", "1e2"]:
            ax.plot(xs, xs * eval(rate), label=f"{rate} calls / sec", marker="", linestyle="-")
        ax.legend()
        ax.set_ylabel("I/O syscalls")
        ax.set_xlabel("Total running time (s)")
        fig.savefig(output / "calls_per_sec.png")

    with (output / "syscalls.txt").open("w") as output_file:
        print("Syscalls:", file=output_file)
        print({
            workload: "{:.0f}".format(
                numpy.mean(df[(df["workload"] == workload) & (df["collector"] == "strace")]["n_ops"])
            )
            for workload in df.workload.cat.categories
        }, file=output_file)
        print("Syscalls per second:", file=output_file)
        print({
            workload: "{:.0f}".format(0)
            for workload in df.workload.cat.categories
        }, file=output_file)



stats_list: list[Callable[[pandas.DataFrame], None]] = [
    performance,
    op_freqs,
    relative,
    minimize,
    bayesian,
    output_features,
]


STATS: Mapping[str, Callable[[pandas.DataFrame], None]] = {
    stat.__name__: stat
    for stat in stats_list
}
