import collections
import tqdm
import hashlib
import urllib.parse
import pathlib
import pandas
import pickle
import charmonium.time_block as ch_time_block
from workloads import WORKLOAD_GROUPS
from prov_collectors import PROV_COLLECTOR_GROUPS
import psutil

proc = psutil.Process()

cache_dir = pathlib.Path(".cache")

prov_collectors = PROV_COLLECTOR_GROUPS["working"]
workloads = WORKLOAD_GROUPS["working-low-mem"]

iterations = 3

size = 256

seed = 0

records = []
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
                    "op_type_counts": collections.Counter(
                        op.type for op in stats.operations
                    ),
                }
                records.append(record)
                print(proc.memory_info().rss // 1024 // 1024, "MiB")

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
