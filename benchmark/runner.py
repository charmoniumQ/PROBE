import functools
import sys
import numpy
import collections
import pandas  # type: ignore
from workloads import WORKLOADS
from prov_collectors import PROV_COLLECTORS, baseline, sciunits, spade_fuse, spade_auditd, bpf_trace, darshan
from experiment import get_results

rel_qois = ["cputime", "walltime", "memory"]
abs_qois = ["storage", "n_ops", "n_unique_files"]
simplest_workload = [
    workload
    for workload in WORKLOADS
    if workload.kind == "simple" and workload.name == "gcc-math-pthread"
][0]

if sys.argv[1] == "test-prov":
    collectors = PROV_COLLECTORS
    workloads = [simplest_workload]
    iterations = 1
elif sys.argv[1] == "test-workloads":
    collectors = [baseline]
    workloads = [
        workload
        for workload in WORKLOADS
    ]
    iterations = 1
elif sys.argv[1] == "fast":
    collectors = PROV_COLLECTORS
    workloads = [
        workload
        for workload in WORKLOADS
        if workload.kind == "simple"
    ]
    iterations = 5
elif sys.argv[1] == "working":
    collectors = PROV_COLLECTORS
    workloads = [
        workload
        for workload in WORKLOADS
        if workload.kind == "data science"
    ]
    iterations = 3
elif sys.argv[1] == "test-genomics":
    collectors = [baseline]
    workloads = [
        workload
        for workload in WORKLOADS
        if workload.kind == "genomics"
    ]
    iterations = 1
elif sys.argv[1] == "sciunits":
    collectors = [sciunits]
    workloads = [simplest_workload]
    iterations = 1
elif sys.argv[1] == "spade_fuse":
    collectors = [spade_fuse]
    workloads = [simplest_workload]
    iterations = 1
elif sys.argv[1] == "spade_auditd":
    collectors = [spade_auditd]
    workloads = [simplest_workload]
    iterations = 1
elif sys.argv[1] == "spade_auditd":
    collectors = [bpf_trace]
    workloads = [simplest_workload]
    iterations = 1
elif sys.argv[1] == "apache":
    collectors = [baseline]
    workloads = [
        workload
        for workload in WORKLOADS
        if workload.kind == "compilation" and workload.name == "apache"
    ]
    iterations = 1
elif sys.argv[1] == "spack":
    collectors = [baseline]
    workloads = [
        workload
        for workload in WORKLOADS
        if workload.kind == "compilation" and type(workload).__name__ == "SpackInstall"
    ][:1]
    iterations = 1
elif sys.argv[1] == "compilation":
    collectors = [baseline]
    workloads = [
        workload
        for workload in WORKLOADS
        if workload.kind == "compilation"
    ]
    iterations = 1
else:
    raise NotImplementedError(sys.argv[1])

df = get_results(collectors, workloads, iterations, seed=0)
show_abs_qois = False
show_rel_qois = False
show_op_freqs = True


@functools.cache
def workload_baseline(workload: str, qoi: str) -> float:
    return numpy.median(
        df[(df["workload"] == workload) & (df["collector"] == baseline.name)][qoi]
    )


if show_abs_qois:
    print(
        df
        .groupby(["workload", "collector"], as_index=True)
        .agg(**{
            **{
                qoi + "_abs_mean": pandas.NamedAgg(
                    column=qoi,
                    aggfunc=numpy.mean,
                )
                for qoi in rel_qois + abs_qois
            },
        })
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


if show_op_freqs:
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


if show_rel_qois:
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
                    ) / workload_baseline(workload, qoi)
                    for workload in df.workload.cat.categories
                ])
                print(f"{value:4.2f}", end=" ")
            print()

    # import matplotlib.figure
    # fig = matplotlib.figure.Figure()
    # ax = fig.add_subplot(1, 1, 1)
    # mat = numpy.array([
    #     list(flatten1(
    #         sorted(df[(df["workload"] == workload) & (df["collector"] == collector)]["walltime"] / workload_baseline[workload])
    #         for collector in collectors
    #     ))
    #     for workload in df.workload.cat.categories
    # ])
    # ax.matshow(mat, vmin=numpy.log(1), vmax=numpy.log(12))
    # print(len(df))
    # n_samples = len(df) // len(df.workload.cat.categories) // len(df.collector.cat.categories)
    # ax.set_xticks(
    #     ticks=range(0, len(collectors) * n_samples, n_samples),
    #     labels=[f"{collector}" for collector in collectors],
    #     rotation=90,
    # )
    # ax.set_yticks(
    #     ticks=range(len(df.workload.cat.categories)),
    #     labels=[
    #         workload
    #         for workload in df.workload.cat.categories
    #     ],
    # )
    # fig.savefig("output/matrix.png")
