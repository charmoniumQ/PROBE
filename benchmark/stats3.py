import polars
import pathlib
import scipy.stats
import util
import stats


iterations = polars.read_parquet("output/iterations.parquet")
agged = polars.read_parquet("output/agged.parquet")
workloads = polars.read_parquet("output/workloads.parquet")


assert workloads["workload_subsubgroup"].n_unique() == len(workloads)


app_groups = {
    "data science": ['titanic-0', 'titanic-1', 'house-prices-0', 'umap', 'hdbscan'],
    "multi-omics": ['blastn', 'blastx', 'blastp', 'megablast', 'tblastn'],
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
        'select-file',
        'select-tcp',
        'protection-fault',
        'install-signal',
        'catch-signal',
        'create/delete',
        'pipe-read/write',
        'read-bandwidth',
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
    if "copy" not in collector
]


ratio = agged.pivot(
    "collector",
    index="workload_subsubgroup",
    values="walltime_overhead_ratio",
).with_columns(polars.col("workload_subsubgroup").cast(str).alias("workload"))


ratios = {
    workload: ratio.filter(polars.col("workload") == workload)[0]
    for group in [*app_groups.values(), *synth_groups.values()]
    for workload in group
}


root = pathlib.Path(__file__).resolve().parent.parent


for file_name, group_names, groups in [("apps", "Applications", app_groups), ("synths", "Synthetic benchmarks", synth_groups)]:
    (root / f"docs/lib_interpos/data_{file_name}.tex").write_text("\n".join([
        r"\begin{tabular}{l" + "c" * len(collectors) + "}",
        r"\toprule",
        rf"\multicolumn{{{len(collectors) + 1}}}{{c}}{{\textbf{{{group_names}}}}} \\\\",
        " & ".join(["workload", *collectors]) + " \\\\",
        r"\midrule",
        " \\\\\n".join([
            " & ".join([
                workload,
                *[
                    "{:.2f}".format(ratios[workload][collector][0])
                    for collector in collectors
                ],
            ])
            for group in groups.values()
            for workload in group
        ]) + " \\\\\n",
        r"\midrule",
        r"\textbf{gmean} & " + " & ".join(
            "{:.2f}".format(scipy.stats.gmean([
                ratios[workload][collector][0]
                for group in groups.values()
                for workload in group
            ]))
            for collector in collectors
        ) + " \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        "",
    ]))
