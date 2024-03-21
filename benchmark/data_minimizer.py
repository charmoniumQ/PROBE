import collections
import tqdm
import hashlib
import urllib.parse
import pathlib
import pandas
import pickle
import random
import charmonium.time_block as ch_time_block
from workloads import WORKLOAD_GROUPS
from prov_collectors import PROV_COLLECTOR_GROUPS, ProvOperation
import psutil

proc = psutil.Process()

cache_dir = pathlib.Path(".cache")

# prov_collectors = PROV_COLLECTOR_GROUPS["working"]
# workloads = WORKLOAD_GROUPS["working-low-mem"]
prov_collectors = PROV_COLLECTOR_GROUPS["fsatrace"]
workloads = WORKLOAD_GROUPS["working"]

iterations = 1

size = 256

seed = 0

rng = random.Random(seed)

def get_overwritten_dependencies(operations: collections.Counter[ProvOperation]) -> set[str]:
    dependencies = set[str]()
    overwritten_dependencies = set[str]()
    for op in operations:
        if op.type.lower() in {"r", "t", "q"}:
            dependencies.add(op.target0)
        elif op.type.lower() in {"w", "m", "d"}:
            if op.target0 in dependencies:
                overwritten_dependencies.add(op.target0)
    return overwritten_dependencies

records = []
workloads_with_overwritten_deps = set[str]()
for prov_collector in prov_collectors:
    for workload in tqdm.tqdm(workloads, desc=f"{prov_collector.name} workloads"):
        for iteration in range(iterations):
            with ch_time_block.ctx(f"Parsing pickle {prov_collector.name} {workload.name}", do_gc=True):
                key = (cache_dir / ("_".join([
                    urllib.parse.quote(prov_collector.name, safe=''),
                    urllib.parse.quote(workload.name, safe=''),
                    str(iteration)
                ]))).with_suffix(".pkl")
                with key.open("rb") as file_obj:
                    stats = pickle.load(file_obj)
                overwritten_deps = get_overwritten_dependencies(stats.operations)
                if overwritten_deps:
                    workloads_with_overwritten_deps.add(workload.name)
                    print(workload.name, "overwritten deps:")
                    k = 10
                    if len(overwritten_deps) > k:
                        test_deps = rng.sample(list(overwritten_deps), 10)
                    else:
                        test_deps = list(overwritten_deps)
                    print("\n".join(test_deps))
                record = {
                    "collector": prov_collector.name,
                    "collector_method": prov_collector.method,
                    "collector_submethod": prov_collector.submethod,
                    "workload": workload.name,
                    "workload_kind": workload.kind,
                    "cputime": stats.cputime,
                    "walltime": stats.walltime,
                    "memory": stats.memory,
                    "storage": stats.provenance_size,
                    "n_ops": len(stats.operations),
                    "n_unique_files": 0,
                    # "n_unique_files": n_unique(itertools.chain(
                    #     (op.target0 for op in stats.operations),
                    #     (op.target1 for op in stats.operations),
                    # )),
                    "raw-dependencies": overwritten_deps,
                    "op_type_counts": collections.Counter(
                        op.type for op in stats.operations
                    ),
                }
                records.append(record)

results_df = (
    pandas.DataFrame.from_records(list(filter(bool, records)))
    .assign(**{
        "collector": lambda df: df["collector"].astype("category"),
        "collector_method": lambda df: df["collector_method"].astype("category"),
        "collector_submethod": lambda df: df["collector_submethod"].astype("category"),
        "workload": lambda df: df["workload"].astype("category"),
        "workload_kind": lambda df: df["workload_kind"].astype("category"),
    })
)
key = (cache_dir / ("results_" + "_".join([
    *[prov_collector.name for prov_collector in prov_collectors],
    hashlib.sha256("".join(sorted(workload.name for workload in workloads)).encode()).hexdigest()[:10],
    str(iterations),
    str(size),
    str(seed),
]) + ".pkl"))
key.write_bytes(pickle.dumps(results_df))
print(workloads_with_overwritten_deps, "workloads with overwritten deps")
