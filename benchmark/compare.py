import collections
import tqdm  # type: ignore
import charmonium.time_block as ch_time
import pathlib
import itertools
import prov_collectors

exe = "result/bin/python"

collectors = [
    prov_collectors.FSATrace(),
    # prov_collectors.STrace(),
    prov_collectors.LTrace(),
]
logs = [
    pathlib.Path(".workdir/artifacts/fsatrace_simple_0"),
    # pathlib.Path(".workdir/artifacts/strace_simple_0"),
    pathlib.Path(".workdir/artifacts/ltrace_simple_0"),
]

with ch_time.ctx("Parsing logs"):
    opss = [
        prov_collector.count(log, exe)
        for prov_collector, log in zip(collectors, logs)
    ]


# for collector, ops in zip(collectors, opss):
#     print(collector)
#     for op in ops:
#         if op.target0 == '/nix/store/1a582hlcr8fhbgv7xba1q712h6i0nnz1-python3-3.10.12-env/bin/Modules/Setup':
#             print(op)
#     print()

with ch_time.ctx(f"Set diffs"):

    filess = [set[pathlib.Path]() for ops in opss]
    for idx, ops in enumerate(opss):
        for op in ops:
            for file in [op.target0, op.target1]:
                if file is not None:
                    path = pathlib.Path(file)
                    if path.exists():
                        filess[idx].add(path)

    for (prov_collector0, ops0, files0), (prov_collector1, ops1, files1) in itertools.permutations(zip(collectors, opss, filess), 2):
        files_only_in0 = files0 - files1
        if files_only_in0:
            ops_only_in0 = collections.Counter(
                op.type if op.type is not None else op.args if op.args is not None else "idk"
                for op in ops0
                if (op.target0 is not None and pathlib.Path(op.target0) in files_only_in0) or (op.target1 is not None and pathlib.Path(op.target1) in files_only_in0)
            )
            print(
                f"{prov_collector1} does not collect {ops_only_in0} that {prov_collector0} collects, leaving out {len(files_only_in0)} files:"
            )
            print("\n".join(sorted(list(map(str, files_only_in0)))))
