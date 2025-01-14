#!/usr/bin/env python
import polars
import pathlib
import scipy.stats
import util
import stats


iterations = polars.read_parquet("output/iterations.parquet")
agged = polars.read_parquet("output/agged.parquet")
workloads = polars.read_parquet("output/workloads.parquet")


assert workloads["workload_subsubgroup"].n_unique() == len(workloads)


print(agged.columns)


polars.Config.set_tbl_rows(1000)


app_groups = {
    "data science": ['titanic-0', 'titanic-1', 'house-prices-0', 'umap', 'hdbscan'],
    "multi-omics": [
        'blastn',
        'blastx',
        'blastp',
        # 'megablast',
        # 'tblastn',
    ],
    # "compilation": ['sextractor'],
}
synth_groups = {
    "exec": ['shell'],
    "lmbench": [
        'syscall',
        'fork',
        'fstat',
        'exec',
        'open/close',
        'write',
        'stat',
        'read',
        # 'select-file',
        # 'select-tcp',
        # 'protection-fault',
        # 'install-signal',
        # 'catch-signal',
        # 'create/delete',
        # 'pipe-read/write',
        # 'read-bandwidth',
    ],
    "postmark": ['postmark',]
}


collectors = sorted(
    agged["collector"].unique(),
    key=lambda collector: stats.collector_order.get(collector, (99, collector)),
)


collectors = [
    collector
    for collector in collectors
    if "copy" not in collector and collector != "noprov"
]


root = pathlib.Path(__file__).resolve().parent.parent


for qty, fn in [("walltime", None), ("max_memory", lambda mem: mem / 1024 / 1024)]:
    if fn is None:
        fn = lambda x: x
    util.console.rule(qty)
    util.console.print(stats.dt_as_seconds(agged).select(
        polars.col("workload_subsubgroup").alias("workload"),
        "collector",
        polars.concat_str(fn(polars.col(f"{qty}_avg")).round(1), polars.lit(" ±"), fn(polars.col(f"{qty}_std")).round(1)).alias(qty)
    ).pivot(
        "collector",
        index="workload",
        values=qty,
    ))


for file_name, group_names, groups in [("apps", "Applications", app_groups), ("synths", "Synthetic benchmarks", synth_groups)]:
    for suffix, col in [("", "walltime_overhead_ratio"), ("_mem", "max_memory_overhead_ratio"), ("_vol_ctx", "n_voluntary_context_switches_overhead_ratio")]:
        util.console.rule(col)
        util.console.print(stats.dt_as_seconds(agged).pivot(
            "collector",
            index="workload_subsubgroup",
            values=col,
        ).select(
            polars.col("workload_subsubgroup").alias("workload"),
            *[
                polars.col(collector).round(1)
                for collector in collectors
            ],
        ))
        (root / f"docs/lib_interpos/data_{file_name}{suffix}.tex").write_text("\n".join([
            r"\begin{tabular}{l" + "c" * len(collectors) + "}",
            r"\toprule",
            rf"\multicolumn{{{len(collectors) + 1}}}{{c}}{{\textbf{{{group_names}}}}} \\\\",
            " & ".join(["workload", *collectors]) + " \\\\",
            r"\midrule",
            " \\\\\n".join([
                " & ".join([
                    workload,
                    *[
                        "{:.2f}".format(agged.filter((polars.col("workload_subsubgroup") == workload) & (polars.col("collector") == collector))[col][0])
                        for collector in collectors
                    ],
                ])
                for group in groups.values()
                for workload in group
            ]) + " \\\\\n",
            r"\midrule",
            r"\textbf{gmean} & " + " & ".join(
                "{:.2f}".format(scipy.stats.gmean([
                    agged.filter((polars.col("workload_subsubgroup") == workload) & (polars.col("collector") == collector))[col][0]
                    for group in groups.values()
                    for workload in group
                ]))
                for collector in collectors
            ) + " \\\\",
            r"\bottomrule",
            r"\end{tabular}",
            "",
        ]))
