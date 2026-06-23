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


@functools.lru_cache
def nix_build(buildable: str) -> pathlib.Path:
    cmd = ["nix", "build", buildable, "--print-out-paths"]
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
        return pathlib.Path(proc.stdout)


@dataclasses.dataclass
class Workload:
    setup: list[str | pathlib.Path] | None
    run: list[str | pathlib.Path]
    context: pathlib.Path


@dataclasses.dataclass
class PrefixTool:
    prefix: list[str | pathlib.Path]

@dataclasses.dataclass
class ProvTracer(PrefixTool):
    pass


root_dir = pathlib.Path(__file__).resolve().parent.parent.resolve()
scratch_dir = root_dir / "scratch"
scratch_dir.mkdir()
results_dir = root_dir / "results"
results_dir.mkdir()
results_file = results_dir / "db.sqlite"
connection = f"sqlite://{results_file!s}"
cpus = [1]
ncpus = 1


podman = lambda image: PrefixTool([
    "podman",
    "run",
    "--volume=/nix/store:/nix/store:ro",
    f"--volume={scratch_dir}/output:rw"
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


timer = PrefixTool([
    nix_build(".#timer") / "bin/timer",
])


tracers = {
    "none": ProvTracer([]),
    "probe": ProvTracer([
        nix_build(".#probe") / "bin/probe",
        "record",
        "--no-transcribe",
    ]),
    "ptu": ProvTracer([
        nix_build(".#provenance_to_use") / "bin/ptu",
    ]),
    "rzip": ProvTracer([
        nix_build(".#reprozip") / "bin/reprozip",
    ])
}


def join_cmds(*cmds: list[str | pathlib.Path]) -> list[str | pathlib.Path]:
    return [
        "sh",
        "-c",
        " && ".join(shlex.join(map(str, cmd)) for cmd in cmds),
    ]


workloads = {
    "resnet/tf-mg": Workload(
        None,
        join_cmds(
            ["python", "10-download.py"],
            ["python", "20-tokenizer.py"],
            ["python", "25-batch.py"],
            ["python", "30-plots.py"],
            ["python", "40-build-transformer.py"],
            ["python", "50-train.py"],
        ),
        reot_dir / "benchmark2/papers_with_code/resnet/tensorflow-model-garden/context",
    ),
}


@functools.lru_cache
def podman_build(context: pathlib.Path, tag: str) -> None:
    subprocess.run(
        ["podman", "build", "--tag", tag, context],
        check=True,
        capture_output=False,
    )


def experiment(
        repetitions: int = 2,
):
    if results_file.exists():
        df = polars.read_database(
            query = "SELECT * FROM experiment", 
            connection=connection,
        )
    else:
        df = polars.DataFrame({
            "tracer": [],
            "workload": [],
            "iteration": [],
            "wall_time": [],
            "cpu_time": [],
            "kernel_time": [],
            "memory": [],
        })
    trials = set(itertools.product(
        tracers.keys(),
        workloads.keys(),
        range(repetitions),
    ))
    trials_to_do = list(trials - set(df.select("tracer", "workload", "iteration")))
    random.Random(0).shuffle(trials_to_do)
    for tracer, workload, iteration in tqdm.tqdm(trials_to_do, desc="trials"):
        if workloads[workload].setup:
            raise NotImplementedError()
        podman_build(workloads[workload].context, workload)
        cmd = podman(workload).prefix + timer.prefix + tracers[tracer].prefix + workloads[workload].run
        proc = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stdout.decode(errors="ignore"))
            print(proc.stderr.decode(errors="ignore"))
            raise NotImplementedError()
        resources = json.loads((scratch_dir / "times.json").read_bytes())
        df = df.vstack(polars.DataFrame({
            "tracer": [tracer],
            "workload": [workload],
            "iteration": [iteration],
            "wall_time": [resources["wall_time"]],
            "cpu_time": [resources["cpu_time"]],
            "kernel_time": [resources["kernel_time"]],
            "memory": [resources["memory"]],
        }))
        df.write_database(
            table_name="experiment",
            connection=connection,
            if_table_exists="replace",
        )
