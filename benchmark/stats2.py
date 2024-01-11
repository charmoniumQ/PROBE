import hashlib
import pathlib
import pymc  # type: ignore
import arviz
import numpy
import charmonium.time_block
from prov_collectors import baseline
from experiment import get_results
from workloads import WORKLOADS
from prov_collectors import PROV_COLLECTORS, baseline

random_seed = 0
cache = pathlib.Path(".cache")

with charmonium.time_block.ctx("getting results"):
    df = get_results(
        [
            collector
            for collector in PROV_COLLECTORS
            if collector != "ltrace"
        ],
        [
            workload
            for workload in WORKLOADS
            if workload.kind != "compilation"
        ],
        iterations=2,
        seed=0,
    )


assert baseline.name in df.collector.cat.categories


with charmonium.time_block.ctx("model"), \
     pymc.Model(coords={
        "data": df.index,
        "workload": df.workload.cat.categories,
        "collector": df.collector.cat.categories,
     }) as model:
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
    is_baseline = df.collector.cat.categories == baseline.name
    workload_runtime = pymc.Exponential(
        "workload_runtime",
        1/50,
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
    collector_runtime_per_syscall = pymc.math.switch(
        is_baseline,
        0,
        pymc.Exponential(
            "collector_runtime_per_syscall",
            1/1.1,
            dims="collector",
        ),
    )
    collector_storage_per_syscall = pymc.math.switch(
        is_baseline,
        pymc.Exponential(
            "collector_storage_per_syscall",
            1/256,
            dims="collector",
        ),
        0,
    )
    workload_collector_runtime = pymc.Deterministic(
        "workload_collector_runtime",
        workload_runtime[workload_idx] + workload_syscalls[workload_idx] * collector_runtime_per_syscall[collector_idx],
        dims=("workload", "collector"),
    )
    workload_collector_overhead = pymc.Detrministic(
        "workload_collector_overhead",
        workload_collector_runtime[workload_idx, collector_idx] / workload_,
        dims=("workload", "collector"),
    )
    # workload_syscalls_per_second = pymc.Deterministic(
    #     "workload_syscalls_per_second",
    #     workload_syscalls / workload_runtime,
    #     dims="workload",
    # )
    runtime_stddev = pymc.Exponential("runtime_stddev", 1/1e-1)
    runtime_mean = workload_runtime[workload_idx] + workload_syscalls[workload_idx] * collector_runtime_per_syscall[collector_idx]
    runtime = pymc.Normal(
        "runtime",
        mu=runtime_mean,
        sigma=runtime_stddev,
        observed=df.walltime,
        dims="data",
    )
    # runtime_rate = pymc.Deterministic(
    #     "runtime_rate",
    #     runtime_mean / runtime_stddev**2,
    # )
    # runtime_count = pymc.Deterministic(
    #     "runtime_count",
    #     runtime_mean**2 / runtime_stddev,
    # )
    storage_stddev = pymc.Exponential("storage_stddev", 1/1024)
    storage = pymc.Normal(
        "storage",
        mu=workload_runtime[workload_idx] * workload_syscalls[workload_idx] * collector_storage_per_syscall[collector_idx],
        sigma=storage_stddev,
        observed=df.storage,
        dims="data",
    )


with charmonium.time_block.ctx("Graphing model"):
    graph = pymc.model_to_graphviz(model)
    graph.render(outfile="output/model.png")
    pathlib.Path("output/model.dot").write_text(graph.source)
    graph_str = hashlib.sha256("\n".join(sorted(graph.source.split("\n"))).encode()).hexdigest()[:10]
    print("model:", graph_str)


with charmonium.time_block.ctx("Prior predictive"):
    cache_file = cache / f"prior-{graph_str}.hdf5"
    if cache_file.exists():
        priors = arviz.from_netcdf(cache_file)  # type: ignore
    else:
        with model:
            priors = pymc.sample_prior_predictive(
                random_seed=random_seed,
            )


with charmonium.time_block.ctx("Plot prior predictive"):
    axes = arviz.plot_ppc(
        priors,
        var_names="runtime",
        group="prior",
    )  # type: ignore
    axes.figure.savefig("output/prior_predictive.png")


with charmonium.time_block.ctx("MCMC"):
    cache_file = cache / f"trace-{graph_str}.hdf5"
    if cache_file.exists():
        trace = arviz.from_netcdf(cache_file)  # type: ignore
    else:
        with model:
            trace = pymc.sample(
                random_seed=random_seed,
                progressbar=True,
                tune=400,
                draws=400,
                chains=3,
            )
            arviz.to_netcdf(trace, cache_file)  # type: ignore

            # check convergence diagnostics
            assert all(arviz.rhat(trace) < 1.03)  # type: ignore

with charmonium.time_block.ctx("Plot MCMC"):
    axes = arviz.plot_trace(
        trace,
        # figsize=(12, 2 * len(trace.posteriors)),
    )
    axes.ravel()[0].figure.savefig("output/trace.png")

    def ident(x):
        return x
    exclude_baseline = {
        "collector": [
            category
            for category in df.collector.cat.categories
            if category not in {"no prov"}
        ],
    }
    variables = [
        ("workload_runtime", "sec", ident, None),
        ("workload_syscalls", "#", ident, None),
        ("collector_runtime_per_syscall", "log sec", numpy.log, exclude_baseline),
        ("collector_storage_per_syscall", "KiB", lambda x: x / 1024, exclude_baseline),
    ]

    for variable, label, transform, coords in variables:
        # axes = arviz.plot_posterior(
        #     trace,
        #     var_names=[variable],
        #     transform=transform,
        #     # coords=coords,
        # ).ravel()
        # figure = axes[0].figure
        # figure.savefig(
        #     f"output/posterior_kde_{variable}.png",
        #     # bbox_inches="tight",
        # )

        axes = arviz.plot_forest(
            trace,
            var_names=[variable],
            transform=transform,
            coords=coords,
            combined=True,
        ).ravel()
        axes[0].set_xlabel(label)
        figure = axes[0].figure
        figure.savefig(
            f"output/posterior_forest_{variable}.png",
            bbox_inches="tight",
        )

with model:
    posteriors = pymc.sample_posterior_predictive(
        trace=trace,
        var_names=["workload_runtime"],
    )

axes = arviz.plot_ppc(
    posteriors,
    var_names=["runtime"],
    observed_rug=True,
).ravel()
figure = axes[0].figure
figure.savefig(
    "output/posterior_predictive_runtimes.png",
    bbox_inches="tight",
)

print("Syscalls:")
print({
    workload: "{.0f}".format(
        numpy.mean(df[(df["workload"] == workload) & (df["collector"] == "strace")]["n_ops"])
    )
    for workload in df.workload.cat.categories
})
print("Syscalls per second:")
print({
    workload: ".0f".format(0)
    for workload in df.workload.cat.categories
})
