import os
import pandas
import pathlib
import numpy
import collections
import abc
import numpy.typing

import pandas
import functools
from typing import Mapping, Callable
from util import flatten1
from prov_collectors import PROV_COLLECTORS
from workloads import WORKLOADS
import operator

rel_qois = ["cputime", "walltime", "memory"]
abs_qois = ["storage", "n_ops", "n_unique_files"]
tmp_output = pathlib.Path("output")
tmp_output.mkdir(exist_ok=True)
output_dir = pathlib.Path("../docs/benchmark_suite/generated")
output_dir.mkdir()

print("The following appear to have failed")
print(df[df["walltime"] < 0.001])


df = (
    df
    # Get rid of unused columns
    # They just soak up memory
    .drop(columns=[col for col in ["collector_method", "collector_submethod"] if col in df.columns])

    # Get rid of "failure" runs which have walltime == 0.0
    [lambda df: df["walltime"] != 0.0]

    # Sciunits runs out of memory on some benchmarks (without failing)
    [lambda df: df["collector"] != "sciunit"]

    # We can refer to the 1st or 2nd run of X workload in Y collector
    .assign(iter=lambda df: df.groupby(["collector", "workload"], observed=True).cumcount())
)

# Rename the benchmarks to match their names in the paper.
df_with_balanced_clusters = (
    df_with_balanced_clusters
    .assign(
        workload_triple=lambda df: [
            {
                "notebook": lambda: (
                    "Data science", "Notebook", {"a-data-sci": "nb-1", "comprehens": "nb-2", "titanic-da": "nb-3"}[name],
                ),
                "archive": lambda: ("Tar", "Archive", name.split(' ')[-1].replace(" archive", "raw").strip()),
                "unarchive": lambda: ("Tar", "Unarchive", name.split(' ')[-1].replace(" unarchive", "raw").strip()),
                "http_server": lambda: ("HTTP", "srv/traffic", name.replace('python http.server', 'simplehttp')),
                "http_client": lambda: ("HTTP", "srv/client", name),
                "ftp_server": lambda: ("FTP", "srv/traffic", name),
                "ftp_client": lambda: ("FTP", "srv/client", name.split('-')[-1].strip()),
                "blast": lambda: ("BLAST", "", "mega" if name == "megablast" else name),
                "shell": lambda: ("Utils", "bash", name),
                "lmbench": lambda: ("IO bench", "lmbench", name.replace('lm-', '').strip()),
                "copy": lambda: ("cp", "", name.split(' ')[-1].strip()),
                "simple": lambda: ("Utils", "", name.strip()),
                "vcs": lambda: ("VCS checkout", "", name.replace('schema-validation', 'hg-repo-1').replace('setuptools_scm', 'git-repo-1').strip()),
                "postmark": lambda: ("IO bench", "postmark", "main"),
                "pdflatex": lambda: ("Compile", "w/latex", name.replace('latex-', '').replace('test2', 'doc2').replace('test', 'doc1').strip()),
                "splash-3": lambda: ("CPU bench", "SPLASH-3", name.split(' ')[-1].split('-')[-1].strip()),
                "spack": lambda: ("Compile", "w/Spack", name.split(' ')[-1].split("~")[0].strip()),
                "gcc": lambda: ("Compile", "w/gcc", name.split(' ')[-1].replace('gcc-', '').strip()),
                "python": lambda: ("Data science", "python", name.strip()),
            }[kind]()
            for kind, name in df[["workload_kind", "workload"]].values
        ],
        collector=lambda df: [
            {
                "care": "CARE",
                "fsatrace": "fsatrace",
                "noprov": "(none)",
                "reprozip": "ReproZip",
                "rr": "RR",
                "strace": "strace",
                "sciunit": "Sciunit",
            }[collector]
            for collector in df["collector"]
        ],
    )
    .assign(
        workload_kind=lambda df: [f"{a} {b}" for a, b, c in df.workload_triple],
        workload_shortname=lambda df: [c for a, b, c in df.workload_triple],
        workload=lambda df: [f"{a} {b} ({c})" for a, b, c in df.workload_triple],
    )
    .assign(
        workload_kind=lambda df: df["workload_kind"].astype("category"),
        workload_shortname=lambda df: df["workload_shortname"].astype("category"),
        workload=lambda df: df["workload"].astype("category"),
        collector=lambda df: df["collector"].astype("category"),
    )
)
collector_order = [
    "(none)",
    "fsatrace",
    "CARE",
    "strace",
    "RR",
    "ReproZip",
]
agged = (
    df_with_balanced_clusters
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
        **{
            f"{qoi}_low": pandas.NamedAgg(qoi, lambda data: numpy.percentile(data, 5))
            for qoi in abs_qois + rel_qois
        },
        **{
            f"{qoi}_high": pandas.NamedAgg(qoi, lambda data: numpy.percentile(data, 95))
            for qoi in abs_qois + rel_qois
        },
        **{
            f"{qoi}_sorted": pandas.NamedAgg(qoi, lambda data: list(sorted(data)))
            for qoi in abs_qois + rel_qois
        },
        "op_type_counts_sum": pandas.NamedAgg(
            "op_type_counts",
            lambda op_type_freqs: functools.reduce(operator.add, op_type_freqs, collections.Counter()),
        ),
        "count": pandas.NamedAgg("walltime", lambda walltimes: len(walltimes)),
        "workload_kind": pandas.NamedAgg("workload_kind", lambda workload_kinds: workload_kinds.iloc[0]),
        "workload_shortname": pandas.NamedAgg("workload_shortname", lambda workload_shortnames: workload_shortnames.iloc[0]),
    })
    .assign(**{
        **{
            f"{qoi}_rel": lambda df, qoi=qoi: df[f"{qoi}_std"] / df[f"{qoi}_mean"]
            for qoi in abs_qois + rel_qois
        },
        "rel_slowdown": lambda df: df["walltime_mean"] / df.loc["(none)"]["walltime_mean"],
        # workload_kind gets set to a String/PyObj in the previous aggregation. This convert it back to categorical
        "workload_kind": lambda df: df["workload_kind"].astype(df_with_balanced_clusters["workload_kind"].dtype),
        "workload_shortname": lambda df: df["workload_shortname"].astype(df_with_balanced_clusters["workload_shortname"].dtype),
    })
    .assign(**{
        "log_rel_slowdown": lambda df: numpy.log(df["rel_slowdown"]),
    })
    .loc[collector_order]
)

assert df["collector"].nunique() == len(collector_order), "not all collectors in df are specified in collector_order"

print(f"Check {tmp_output} for best and worst slowdowns; sometimes that indicates there is an error")
for collector in agged.index.levels[0]:
    fig = matplotlib.figure.Figure()
    ax = fig.add_subplot(1, 1, 1)
    ax = agged.loc[collector]["rel_slowdown"].nlargest(20).plot.bar(ax=ax)
    ax.set_title(f"{collector} worst slowdown")
    ax.set_ylabel("Slowdown ratio")
    fig.savefig(tmp_output / "worst_slowdowns_{collector}.png")

for collector in agged.index.levels[0]:
    fig = matplotlib.figure.Figure()
    ax = fig.add_subplot(1, 1, 1)
    ax = agged.loc[collector]["rel_slowdown"].nsmallest(20).plot.bar(ax=ax)
    ax.set_title(f"{collector} best slowdown")
    ax.set_ylabel("Slowdown ratio")
    fig.savefig(tmp_output / "best_slowdowns_{collector}.png")

print("All benchmarks:", ", ".join(agged.index.levels[1]))

log_to_human_readable = lambda series: r"{:.0f}".format(
    100 * (numpy.exp(numpy.mean(series)) - 1),
    # 100 * (
    #     (numpy.exp(numpy.mean(series) + numpy.std(series)) - numpy.exp(numpy.mean(series) - numpy.std(series)))
    #     / 2
    # ),
)

file = output_dir / "benchmark_groups_by_slowdown.tex"
print(f"Writing {file}")
file.write_text(
    agged
    .reset_index()
    .groupby(["collector", "workload_kind"], observed=True)
    .agg({"log_rel_slowdown": "mean"})
    .assign(**{
        "gmean": lambda df: [
            log_to_human_readable(x)
            for x in df.log_rel_slowdown
        ],
    })
    .reset_index()
    .pivot(index="collector", columns="workload_kind", values="gmean")
    .pipe(lambda df: (df.index.__setattr__("name", None), df)[1])
    .pipe(lambda df: (df.columns.__setattr__("name", None), df)[1])
    .loc[collector_order]
    .transpose()
    .to_latex()
    .replace("\\bottomrule", "\n".join([
        r"\midrule",
        "Total (gmean) & " + " & ".join(list(
            agged
            .groupby(level=0, observed=True)
            .agg(**{
                "gmean": pandas.NamedAgg("log_rel_slowdown", log_to_human_readable),
            })
            .transpose()
            [collector_order]
            .loc["gmean"]
        )) + r" \\",
        r"\bottomrule",
    ]))
)



