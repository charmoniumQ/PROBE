import pathlib
import pandas
import numpy
import functools
import collections
from typing import Mapping, Callable
from util import flatten1
from prov_collectors import PROV_COLLECTORS
from workloads import WORKLOADS


rel_qois = ["cputime", "walltime", "memory"]
abs_qois = ["storage", "n_ops", "n_unique_files"]


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
    print(
        mean_df
        .drop(["cputime_abs_mean", "memory_abs_mean", "n_unique_files_abs_mean"], axis=1)
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
            "Unique files": lambda val: f"{val:.0f}",
        })
    )
    total = mean_df.loc[:, "walltime_abs_mean"].sum()
    print(f"Noprov total {total:.0f}s")


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


@functools.cache
def _workload_baseline(df: pandas.DataFrame, workload: str, qoi: str) -> float:
    return numpy.median(
        df[(df["workload"] == workload) & (df["collector"] == "noprov")][qoi]
    )


def relative_performance(df: pandas.DataFrame):
    for qoi in ["walltime"]:
        collectors = sorted(
            df.collector.cat.categories,
            key=lambda collector: numpy.mean([
                df[(df["workload"] == workload) & (df["collector"] == collector)][qoi]
                for workload in df.workload.cat.categories
            ])
        )
        for collector in collectors:
            print(f"{collector:10s}", end=" ")
            for rank in [5, 50, 95]:
                value = numpy.mean([
                    numpy.percentile(
                        df[(df["workload"] == workload) & (df["collector"] == collector)][qoi],
                        rank,
                    ) / _workload_baseline(df, workload, qoi)
                    for workload in df.workload.cat.categories
                ])
                print(f"{value:4.2f}", end=" ")
            print()

    import matplotlib.figure
    fig = matplotlib.figure.Figure()
    ax = fig.add_subplot(1, 1, 1)
    mat = numpy.array([
        list(flatten1(
            sorted(df[(df["workload"] == workload) & (df["collector"] == collector)]["walltime"] / _workload_baseline(df, workload, "walltime"))
            for collector in collectors
        ))
        for workload in df.workload.cat.categories
    ])
    ax.matshow(mat, vmin=numpy.log(1), vmax=numpy.log(12))
    print(len(df))
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
    fig.savefig("output/matrix.png")


def minimize(df: pandas.DataFrame):
    output = pathlib.Path() / "output"
    output.mkdir(exist_ok=True)
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
    collectors = list(mean_df.index)
    workloads = list(mean_df.columns)
    data = mean_df.to_numpy()
    import scipy.linalg
    collectors_proj, singular_values, workloads_proj = scipy.linalg.svd(
        data
    )
    workload_to_kind = {
        workload.name: workload.kind
        for workload in WORKLOADS
    }
    import matplotlib.colors
    import matplotlib.cm
    kind_to_color = dict(zip(
        sorted(list(set(workload.kind for workload in WORKLOADS))),
        sorted(matplotlib.cm.Dark2.colors + matplotlib.cm.Set2.colors),
    ))
    (output / "sing_val").write_text("Singular values: " + "\n".join([f"{i: >3d}: {x:.1f}" for i, x in enumerate(singular_values)]) + "\n")
    import scipy.linalg.interpolative
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
        import matplotlib.figure
        import matplotlib.legend
        import matplotlib.lines
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


stats_list: list[Callable[[pandas.DataFrame], None]] = [
    performance,
    op_freqs,
    relative_performance,
    minimize,
]


STATS: Mapping[str, Callable[[pandas.DataFrame], None]] = {
    stat.__name__: stat
    for stat in stats_list
}
