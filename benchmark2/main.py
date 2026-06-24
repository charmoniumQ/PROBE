import shutil
import json
import tqdm
import random
import itertools
import polars
import functools
import subprocess
import dataclasses
import pathlib
import shlex


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
class PrefixTool:
    prefix: list[str | pathlib.Path]


@dataclasses.dataclass
class ProvTracer(PrefixTool):
    make_artifact: list[str | pathlib.Path] | None
    artifact: pathlib.Path | None


root_dir = pathlib.Path(__file__).resolve().parent.parent.resolve()
scratch_dir = root_dir / ".cache"
scratch_dir.mkdir(exist_ok=True)
results_dir = root_dir / ".results"
results_dir.mkdir(exist_ok=True)
results_file = results_dir / "db.sqlite"
connection = f"sqlite:///{results_file!s}"
cpus = [1]
ncpus = 1
time_json = scratch_dir / "time.json"


podman = lambda image, mounts: PrefixTool([
    "podman",
    "run",
    "--volume=/nix/store:/nix/store:ro",
    f"--volume={scratch_dir}:/scratch:rw",
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
])


timer_thunk = lambda: PrefixTool([
    nix_build("nixpkgs#time") / "bin/time",
    "--format",
    '{"wall_time": %e, "kernel_time": %s, "user_time": %U, "memory": %M, "returncode": %x}',
    "--output",
    "/scratch/time.json",
])


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
            ["python", "/scripts/20-tokenizer.py"],
        ),
        join_cmds(
            ["python", "/scripts/10-download.py"],
            ["python", "/scripts/20-tokenizer.py"],
            ["python", "/scripts/25-batch.py"],
            ["python", "/scripts/30-plots.py"],
            ["python", "/scripts/40-build-transformer.py"],
            ["python", "/scripts/50-train.py"],
        ),
        root_dir / "benchmark2/resnet-tf-mg/context",
        [
            (root_dir / "benchmark2/resnet-tf-mg/scripts", pathlib.Path("/scripts"), "ro")
        ]
    ),
    "touch": Workload(
        None,
        ["touch", "test"],
        root_dir / "benchmark2/resnet-tf-mg/context",
        [],
    )
}


@functools.lru_cache
def podman_build(context: pathlib.Path, tag: str) -> None:
    subprocess.run(
        ["podman", "build", "--tag", tag, context],
        check=True,
        capture_output=False,
    )


repetitions = 2
schema = {
    "tracer": str,
    "workload": str,
    "iteration": polars.Int64,
    "wall_time": polars.Float64,
    "cpu_time": polars.Float64,
    "kernel_time": polars.Float64,
    "memory": polars.Float64,
}
import sqlalchemy
engine = sqlalchemy.create_engine(connection)
if sqlalchemy.inspect(engine).has_table("experiment"):
    df = polars.read_database(
        query="SELECT * FROM experiment", 
        connection=engine,
    )
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
trials = set(itertools.product(
    tracers.keys(),
    workloads.keys(),
    range(repetitions),
))
trials_done = set(df.select(["tracer", "workload", "iteration"]).rows())
trials_to_do = list(trials - trials_done)
random.Random(0).shuffle(trials_to_do)
print("initial")
print(df)
for tracer_name, workload_name, iteration in tqdm.tqdm(trials_to_do, desc="trials"):
    timer = timer_thunk()
    workload = workloads[workload_name]
    tracer = tracers[tracer_name]()
    if workload.setup:
        cmd = podman(workload_name, workload.mounts).prefix + workload.run
        print(f"Running {tracer_name} {workload_name} setup")
        print(shlex.join(map(str, cmd)))
        proc = subprocess.run(
            cmd,
            check=True,
        )
    podman_build(workload.context, workload_name)
    if time_json.exists():
        time_json.unlink()
    cmd = podman(workload_name, workload.mounts).prefix + timer.prefix + tracer.prefix + workload.run
    print(f"Running {tracer_name} {workload_name}")
    print(shlex.join(map(str, cmd)))
    proc = subprocess.run(
        cmd,
        check=True,
    )
    resources = json.loads(time_json.read_bytes() if time_json.exists() else "{}")
    if resources.get("returncode") != 0:
        print(shlex.join(map(str, cmd)))
        raise RuntimeError()

    if tracer.make_artifact and iteration == 0:
        cmd = podman(workload_name, workload.mounts).prefix + tracer.make_artifact
        print(f"Running {tracer_name} {workload_name} artifact")
        print(shlex.join(map(str, cmd)))
        proc = subprocess.run(
            cmd,
            check=True,
        )
        assert tracer.artifact
        artifact_path = results_dir / "artifacts" / tracer_name / workload_name
        artifact_path.parent.mkdir(exist_ok=True, parents=True)
        if artifact_path.exists():
            artifact_path.unlink()
        shutil.move(scratch_dir / tracer.artifact, artifact_path)
    df = df.vstack(polars.DataFrame({
        "tracer": [tracer_name],
        "workload": [workload_name],
        "iteration": [iteration],
        "wall_time": [resources["wall_time"]],
        "cpu_time": [resources["user_time"]],
        "kernel_time": [resources["kernel_time"]],
        "memory": [float(resources["memory"])],
    }, schema=schema))
    df.write_database(
        table_name="experiment",
        connection=engine,
        if_table_exists="replace",
    )
print("done")
print(df)
