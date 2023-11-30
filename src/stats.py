import hashlib
import pathlib
import pymc  # type: ignore
import arviz
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
            if collector.name != "ltrace"
        ],
        [
            workload
            for workload in WORKLOADS
            if workload.kind == "data science"
        ],
        iterations=3,
        seed=0,
    )


assert baseline.name in df.collector.cat.categories
baseline_collector_idx = next(code for (code, categ) in enumerate(df.collector.cat.categories) if categ == baseline.name)


# priors = "2-level-normal"
priors = "exponential"


with charmonium.time_block.ctx("model"), \
     pymc.Model(coords={
        "data": df.index,
        "workload": df.workload.cat.categories,
        "collector": df.collector.cat.categories,
     }) as model:
    workload_idx = pymc.Data(
        "workload_idx",
        df.workload.cat.codes,
        dims="data",
        mutable=False,
    )
    collector_idx = pymc.Data(
        "collector_idx",
        df.collector.cat.codes,
        dims="data",
        mutable=False,
    )

    if priors == "2-level-normal":
        pooled_workload_runtime_mean = pymc.Exponential(
            "pooled_workload_runtime_mean", 1/50
        )
        pooled_workload_runtime_stddev = pymc.Exponential(
            "pooled_workload_runtime_stddev", 1/1
        )
        workload_runtime = pymc.Normal(
            "workload_runtime",
            mu=pooled_workload_runtime_mean,
            sigma=pooled_workload_runtime_stddev,
            dims="workload",
        )
        raise NotImplementedError("workload ops")
    elif priors == "exponential":
        workload_runtime = pymc.Exponential(
            "workload_runtime",
            1/50,
            dims="workload",
        )
    else:
        raise NotImplementedError(priors)

    if priors == "2-level-normal":
        pooled_collector_overhead_mean = pymc.Exponential(
            "pooled_collector_overhead_mean", 1/1e-1
        )
        pooled_collector_overhead_stddev = pymc.Exponential(
            "pooled_collector_overhead_stddev", 1/1e-2
        )
        collector_overhead = pymc.Normal(
            "collector_overhead",
            mu=pooled_collector_overhead_mean,
            sigma=pooled_collector_overhead_stddev,
            dims="collector",
        )
        pooled_collector_storage_rate_mean = pymc.Exponential(
            "pooled_collector_storage_rate_mean", 1/1024
        )
        pooled_collector_storage_rate_stddev = pymc.Exponential(
            "pooled_collector_storage_rate_stddev", 1/1024
        )
        collector_storage_rate = pymc.Normal(
            "collector_storage_rate",
            mu=pooled_collector_storage_rate_mean,
            sigma=pooled_collector_storage_rate_stddev,
            dims="collector",
        )
    elif priors == "exponential":
        collector_overhead = pymc.Exponential(
            "collector_overhead",
            1/1.1,
            dims="collector",
        )
        collector_storage_rate = pymc.Exponential(
            "collector_storage_rate",
            1/1024,
            dims="collector",
        )
    else:
        raise NotImplementedError(priors)

    est_runtime = pymc.Deterministic(
        "est_runtime",
        (
            workload_runtime[workload_idx] * (1 + pymc.math.switch(
                df.collector.cat.codes == baseline_collector_idx,
                0,
                collector_overhead[collector_idx],
            ))
        ),
        dims="data",
    )
    runtime_stddev = pymc.Exponential("runtime_stddev", 1/1e-1)
    runtime = pymc.Normal(
        "runtime",
        mu=est_runtime,
        sigma=runtime_stddev,
        observed=df.walltime,
        dims="data",
    )

    est_storage = pymc.Deterministic(
        "est_storage",
        workload_runtime[workload_idx] * (1 + pymc.math.switch(
            df.collector.cat.codes == baseline_collector_idx,
            0,
            collector_storage_rate[collector_idx],
        )),
        dims="data",
    )
    storage_stddev = pymc.Exponential("storage_stddev", 1/1024)
    storage = pymc.Normal(
        "storage",
        mu=est_storage,
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
    axes = arviz.plot_ppc(priors, var_names="runtime", group="prior")  # type: ignore
    axes.figure.savefig("output/prior_runtime.png")


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
    # axes = arviz.plot_trace(trace)
    # axes.ravel()[0].figure.savefig("output/trace.png")

    # axes = arviz.plot_posterior(trace, var_names=[  # type: ignore
    #     "pooled_workload_runtime_mean", "pooled_collector_overhead_mean", "runtime_std"
    # ])
    # axes.ravel()[0].figure.savefig("output/global_posteriors.png")

    axes = arviz.plot_forest(trace, var_names="workload_runtime", combined=True)  # type: ignore
    ax = axes.ravel()[0]
    ax.figure.savefig("output/workload_posteriors.png", bbox_inches="tight")

    coords = {"collector": [category for category in df.collector.cat.categories if category not in {"no prov", "reprozip"}]}
    axes = arviz.plot_forest(
        trace,
        var_names=["collector_overhead"],
        coords=coords,
        combined=True,
        hdi_prob=0.94,
        transform=lambda x: x + 1,
        ridgeplot_overlap=0.5,
        kind="forestplot",
        ess=True,
        r_hat=True,
    )  # type: ignore
    ax = axes.ravel()[0]
    ax.figure.savefig("output/collector_overhead.png", bbox_inches="tight")

    axes = arviz.plot_forest(
        trace,
        var_names=["collector_storage_rate"],
        coords=coords,
        combined=True,
        hdi_prob=0.94,
        transform=lambda x: x + 1,
        ridgeplot_overlap=0.5,
        kind="forestplot",
        ess=True,
        r_hat=True,
    )  # type: ignore
    ax = axes.ravel()[0]
    ax.figure.savefig("output/collector_storage_rate.png", bbox_inches="tight")

    with model:
        posterior = pymc.sample_posterior_predictive(
            trace=trace,
            var_names=["collector_overhead"],
        )

    marks = posterior.posterior_predictive.collector_overhead.quantile([0.05, 0.5, 0.95], dim=["chain", "draw"])
    collectors = sorted(
        [
            (collector_idx, collector)
            for collector_idx, collector in enumerate(df.collector.cat.categories)
        ],
        key=lambda pair: marks[1][pair[0]],
    )
    print()
    for collector_idx, collector in collectors:
        if collector != "no prov":
            print("{} {:3.1f} {:3.1f} {:3.1f}".format(
                collector,
                marks[0][collector_idx],
                marks[1][collector_idx],
                marks[2][collector_idx],
           ))
