import collections.abc
import dataclasses
import functools
import itertools
import json
import pathlib
import random
import shlex
import shutil
import subprocess
import typing

import polars
import tqdm
import yaml


def join_cmds(*cmds: list[str | pathlib.Path]) -> list[str | pathlib.Path]:
    return [
        "sh",
        "-c",
        " && ".join(shlex.join(map(str, cmd)) for cmd in cmds),
    ]


@functools.lru_cache
def nix_build(buildable: str) -> pathlib.Path:
    print(f"Building: {buildable}")
    cmd = ["nix", "build", buildable, "--print-out-paths", "--show-trace"]
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True
    )
    if proc.returncode != 0:
        print(proc.stderr)
        print(proc.stdout)
        raise RuntimeError()
    else:
        assert proc.stdout.count("\n") == 1
        assert proc.stdout.startswith("/nix/store/")
        return pathlib.Path(proc.stdout.strip())


@dataclasses.dataclass
class Workload:
    setup: list[str | pathlib.Path] | None
    run: list[str | pathlib.Path]
    context: pathlib.Path
    mounts: list[tuple[pathlib.Path, pathlib.Path, str]]


@dataclasses.dataclass
class ProvTracer:
    prefix: list[str | pathlib.Path]
    make_artifact: list[str | pathlib.Path] | None
    artifact: pathlib.Path | None


root_dir = pathlib.Path(__file__).resolve().parent.parent.resolve()
scratch_dir = root_dir / ".cache"
scratch_dir.mkdir(exist_ok=True)
results_dir = root_dir / ".results"
results_dir.mkdir(exist_ok=True)
results_file = results_dir / "db.parquet"
cpus = [1]
ncpus = 1
time_json = scratch_dir / "time.yaml"
benchmark_utils = pathlib.Path("~/.cache/cargo-builds/debug").expanduser()


stabilize = [
    benchmark_utils / "systemd-stabilize",
    "--reserved-cpus=0",
    # f"--reserved-memory={1024*1024*1024}",
    "--",
    benchmark_utils / "host-stabilize",
    "--reserved-cpus=0",
    "--disable-smt",
    "--disable-freq-scaling",
    "--drop-fs-cache",
    "--",
]


podman = lambda image, mounts: [
    "podman",
    "run",
    "--volume=/nix/store:/nix/store:ro",
    f"--volume={scratch_dir}:/scratch:rw",
    f"--volume={benchmark_utils}:{benchmark_utils}:ro",
    *([
        f"--volume={src!s}:{dst!s}:{mode}"
        for src, dst, mode in mounts
    ]),
    # Not needed if we use PROBE from /nix/store
    # "--env", f"PROBE_LIB={path_to_probe_lib}",
    # "--env", f"probe={path_to_probe_bin}",
    # "--volume", "$PROBE_LIB:${PROBE_LIB}:ro",
    # "--volume", "$(dirname $(which probe)):$(dirname $(which probe)):ro",
    # "--volume", "$PROBE_ROOT:$PROBE_ROOT:ro",
    f"--cpuset-cpus={','.join(map(str, cpus))}",
    f"--cpus={ncpus}",
    "--rm",
    image,
]


no_random = [benchmark_utils / "no-random"]


timer = [
    benchmark_utils / "process-stabilize",
    # "--disable-aslr",
    "--repetitions=1",
    # "--key=",
    "/scratch/time.yaml",
    "--",
]


tracers = {
    "none": lambda: ProvTracer([], None, None),
    "probe": lambda: ProvTracer(
        [
            nix_build(".#probe") / "bin/probe",
            "record",
            "--copy-files=none",
            "--no-transcribe",
            "--overwrite",
        ],
        None,
        None,
    ),
    "probe-2": lambda: ProvTracer(
        [
            nix_build(".#probe") / "bin/probe",
            "record",
            "--copy-files=none",
            "--output=/scratch/probe_log",
            "--overwrite",
        ],
        [
            nix_build(".#probe") / "bin/probe",
            "py",
            "export",
            "dataflow-graph",
            "--probe-log=/scratch/probe_log",
            "/scratch/dataflow-graph.dot",
            "--loose",
        ],
        pathlib.Path("dataflow-graph.dot"),
    ),
    "ptu": lambda: ProvTracer(
        [
            nix_build(".#provenance-to-use-dir") / "bin/ptu",
            "/scratch/cde-package",
        ],
        None,
        pathlib.Path("cde-package/provenance.cde-root.1.log"),
    ),
    "rzip": lambda: ProvTracer(
        [
            nix_build(".#reprozip") / "bin/reprozip",
            "trace",
            "--overwrite",
            "--dir=/scratch/rpz",
        ],
        join_cmds(
            ["rm", "--force", "/scratch/provenance.dot"],
            [
                nix_build(".#reprounzip") / "bin/reprounzip",
                "graph",
                "/scratch/provenance.dot",
                "--dir=/scratch/rpz",
            ]
        ),
        pathlib.Path("provenance.dot"),
    ),
}


workloads = {
    "resnet-tf-mg": Workload(
        join_cmds(
            ["python", "/scripts/10-download.py"],
        ),
        join_cmds(
            ["env", "-", "python", "/scripts/10-download.py"],
            ["env", "-", "python", "/scripts/20-tokenizer.py"],
            ["env", "-", "python", "/scripts/25-batch.py"],
            ["env", "-", "python", "/scripts/30-plots.py"],
            ["env", "-", "python", "/scripts/40-build-transformer.py"],
            ["env", "-", "python", "/scripts/50-train.py"],
        ),
        root_dir / "benchmark2/resnet-tf-mg/context",
        [
            (root_dir / "benchmark2/resnet-tf-mg/scripts", pathlib.Path("/scripts"), "ro")
        ]
    ),
    # "touch": Workload(
    #     None,
    #     ["touch", "test"],
    #     root_dir / "benchmark2/resnet-tf-mg/context",
    #     [],
    # )
}


@functools.lru_cache
def podman_build(context: pathlib.Path, tag: str) -> None:
    subprocess.run(
        ["podman", "build", "--tag", tag, context],
        check=True,
        capture_output=False,
    )


def do_trial(tracer_name: str, workload_name: str) -> collections.abc.Mapping[str, typing.Any]:
    workload = workloads[workload_name]
    tracer = tracers[tracer_name]()

    podman_build(workload.context, workload_name)

    if workload.setup:
        cmd = podman(workload_name, workload.mounts) + workload.run
        print(f"Running {tracer_name} {workload_name} setup")
        print(shlex.join(map(str, cmd)))
        subprocess.run(
            cmd,
            check=True,
        )
    if time_json.exists():
        time_json.unlink()

    cmd = stabilize + podman(workload_name, workload.mounts) + no_random + timer + tracer.prefix + workload.run
    print(f"Running {tracer_name} {workload_name}")
    print(shlex.join(map(str, cmd)))
    subprocess.run(
        cmd,
        check=True,
    )

    resources = yaml.load(time_json.read_bytes() if time_json.exists() else "{}", Loader=TupleKeyLoader)

    # if tracer.make_artifact and iteration == 0:
    #     cmd = podman(workload_name, workload.mounts) + tracer.make_artifact
    #     print(f"Running {tracer_name} {workload_name} artifact")
    #     print(shlex.join(map(str, cmd)))
    #     subprocess.run(
    #         cmd,
    #         check=True,
    #     )
    #     assert tracer.artifact
    #     artifact_path = results_dir / "artifacts" / tracer_name / workload_name
    #     artifact_path.parent.mkdir(exist_ok=True, parents=True)
    #     if artifact_path.exists():
    #         artifact_path.unlink()
    #     shutil.move(scratch_dir / tracer.artifact, artifact_path)

    return resources


class TupleKeyLoader(yaml.SafeLoader):
    pass

def construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if isinstance(key, list):
            key = tuple(key)
        value = loader.construct_object(value_node, deep=True)
        mapping[key] = value
    return mapping

TupleKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping,
)


repetitions = 5
schema = {
    "tracer": polars.Categorical(),
    "workload": polars.Categorical(),
    "iteration": polars.Int8(),
    "wall_time": polars.datatypes.Duration("us"),
    "cpu_time": polars.datatypes.Duration("us"),
    "kernel_time": polars.datatypes.Duration("us"),
    "memory": polars.UInt64(),
}
if results_file.exists():
    df = polars.read_parquet(results_file)
else:
    df = polars.DataFrame(
        data={
            "tracer": [],
            "workload": [],
            "iteration": [],
            "wall_time": [],
            "cpu_time": [],
            "kernel_time": [],
            "memory": [],
        },
        schema=schema,
    )

print("initial")
print(df)


trials_done = set(df.select(["tracer", "workload", "iteration"]).rows())
for it in range(repetitions):
    trials = set(itertools.product(
        tracers.keys(),
        workloads.keys(),
        (it,),
    ))
    trials_to_do = list(trials - trials_done)
    random.Random(0).shuffle(trials_to_do)
    for tracer_name, workload_name, iteration in tqdm.tqdm(trials_to_do, desc="trials"):
        resources = do_trial(tracer_name, workload_name)
        df = df.vstack(polars.DataFrame({
            "tracer": [tracer_name],
            "workload": [workload_name],
            "iteration": [iteration],
            "wall_time": [resources["rusage"]["stop"] - resources["rusage"]["start"]],
            "cpu_time": [resources["rusage"]["cpu_user_us"]],
            "kernel_time": [resources["rusage"]["cpu_system_us"]],
            "memory": [resources["rusage"]["peak_memory_usage"]],
        }, schema=schema))
        df.write_parquet(results_file)
print("done")
print(df)
