import collections
import collections.abc
import dataclasses
import functools
import itertools
import json
import pathlib
import random
import re
import shlex
import shutil
import subprocess
import typing

import polars
import sqlite3
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
    run: list[tuple[str, list[str | pathlib.Path]]]
    context: pathlib.Path
    mounts: list[tuple[pathlib.Path, pathlib.Path, str]]
    inputs: list[str]
    outputs: list[str]


@dataclasses.dataclass
class ProvTracer:
    prefix: list[str | pathlib.Path]
    make_artifact: list[str | pathlib.Path] | None
    artifact: pathlib.Path | None
    count_ops: typing.Callable[[], collections.abc.Mapping[str, int]]


root_dir = pathlib.Path(__file__).resolve().parent.parent.resolve()
scratch_dir = root_dir / ".scratch"
scratch_dir.mkdir(exist_ok=True)
results_dir = root_dir / ".results"
results_dir.mkdir(exist_ok=True)
results_file = results_dir / "db.parquet"
output_dir = root_dir / ".results" / "output"
output_dir.mkdir(exist_ok=True)
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
    "--disable-aslr",
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
    "--interactive", # allows stdin, needed for MCP model server in experiment2.py
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
    "--repetitions=1",
    # "--key=",
    "/scratch/time.yaml",
    "--",
]


tracers = {
    "none": lambda: ProvTracer([], None, None, lambda: {}),
    "strace": lambda: ProvTracer(
        [
            nix_build(".#strace.out") / "bin/strace",
            "--follow-forks",
            "--output=/scratch/strace.log"
        ],
        None,
        None,
        lambda: strace_counts(scratch_dir / "strace.log"),
    ),
    "probe-fast": lambda: ProvTracer(
        [
            nix_build(".#probe") / "bin/probe",
            "record",
            "--copy-files=none",
            "--no-transcribe",
            "--overwrite",
        ],
        None,
        None,
        lambda: {},
    ),
    "probe-slow": lambda: ProvTracer(
        [
            nix_build(".#probe") / "bin/probe",
            "record",
            "--copy-files=eagerly",
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
        lambda: probe_counts(scratch_dir / "probe_log"),
    ),
    "ptu": lambda: ProvTracer(
        [
            nix_build(".#provenance-to-use-dir") / "bin/ptu",
            "/scratch/cde-package",
        ],
        None,
        pathlib.Path("cde-package/provenance.cde-root.1.log"),
        lambda: ptu_counts(scratch_dir / "cde-package/provenance.cde-root.1.log"),
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
        lambda: reprozip_counts(scratch_dir / "rpz/trace.sqlite3")
    ),
}


def probe_counts(log: pathlib.Path) -> collections.abc.Mapping[str, int]:
    proc = subprocess.run(
        ["probe", "py", "op-counts", "--probe-log", str(log)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout.strip().split("\n")[-1])


def strace_counts(log: pathlib.Path) -> collections.abc.Mapping[str, int]:
    line_regex = re.compile(r"^(?P<pid>\d+) +(?P<op>.+?)\(")
    pids = set()
    ops = collections.Counter[str]()
    for line in log.read_text().split("\n"):
        if match := line_regex.match(line):
            pids.add(int(match.group("pid")))
            ops[match.group("op")[:7]] += 1
    return {**ops, "pids": len(pids)}


def ptu_counts(log: pathlib.Path) -> collections.abc.Mapping[str, int]:
    line_regex = re.compile(r"(?P<time>\d+) (?P<pid>\d+) (?P<op>[A-Z]+)")
    pids = set()
    ops = collections.Counter[str]()
    for line in log.read_text().split("\n"):
        if match := line_regex.match(line):
            pids.add(int(match.group("pid")))
            ops[match.group("op")[:7]] += 1
    return {**ops, "pids": len(pids)}


def reprozip_counts(db: pathlib.Path) -> collections.abc.Mapping[str, int]:
    connection = sqlite3.connect(db)
    cursor = connection.cursor()
    return {
        table: cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in [
                "executed_files",
                "opened_files",
                "processes",
        ]
    }


workloads = {
    "resnet-tf-mg": Workload(
        setup=join_cmds(
            ["python", "/scripts/10-download.py"],
        ),
        run=[
            ("download", ["env", "-", "python", "/scripts/10-download.py"]),
            ("tokenize", ["env", "-", "python", "/scripts/20-tokenizer.py"]),
            ("batch", ["env", "-", "python", "/scripts/25-batch.py"]),
            ("plots", ["env", "-", "python", "/scripts/30-plots.py"]),
            ("transformer", ["env", "-", "python", "/scripts/40-build-transformer.py"]),
            ("train", ["env", "-", "python", "/scripts/50-train.py"]),
            ("inference", ["env", "-", "python", "/scripts/60-inference.py"]),
        ],
        context=root_dir / "benchmark2/resnet-tf-mg/context",
        mounts=[
            (root_dir / "benchmark2/resnet-tf-mg/scripts", pathlib.Path("/scripts"), "ro")
        ],
        outputs=[
            "/output/trained_model.*",
            "/output/val_batches/*.pb",
            "/output/train_batches/*.pb",
            "/output/val_examples/*.pb",
            "/output/train_examples/*.pb",
            "/output/token_lengths.png",
            "/output/ted_hrlr_translate_pt_en_converter_extracted/ted_hrlr_translate_pt_en_converter/saved_model.pb",
            "/output/ted_hrlr_translate_pt_en_converter.zip",
        ],
        inputs=[
            "/scripts/*.py",
            "/usr/local/lib/python3.11/dist-packages/tensorflow/__init__.py",
        ],
    ),
    "simple": Workload(
        ["python", "-c", "import pathlib, random\npathlib.Path('/scratch/test.txt').write_text(''.join(chr(random.randint(0, 127)) for _ in range(1000)))"],
        [
            ("open-close", ["python", "-c", "import pathlib\nfor _ in range(100):\n  pathlib.Path('/scratch/test.txt').read_text()"]),
        ],
        context=root_dir / "benchmark2/resnet-tf-mg/context",
        mounts=[],
        outputs=[
            "/scratch/test.txt",
        ],
        inputs=[
            "/usr/bin/python",
        ]
    )
}


@functools.lru_cache
def podman_build(context: pathlib.Path, tag: str) -> None:
    subprocess.run(
        ["podman", "build", "--tag", tag, context],
        check=True,
        capture_output=False,
    )


def do_trial(tracer_name: str, workload_name: str) -> collections.abc.Iterator[tuple[str, collections.abc.Mapping[str, typing.Any], collections.abc.Mapping[str, typing.Any]]]:
    workload = workloads[workload_name]
    tracer = tracers[tracer_name]()

    podman_build(workload.context, workload_name)

    if workload.setup:
        cmd = podman(workload_name, workload.mounts) + workload.setup
        print(f"Running {tracer_name} {workload_name} setup")
        print(shlex.join(map(str, cmd)))
        subprocess.run(
            cmd,
            check=True,
        )

    (output_dir / workload_name).mkdir(exist_ok=True)
    for label, stage_cmd in workload.run:
        if time_json.exists():
            time_json.unlink()
        mounts = [*workload.mounts, (output_dir / workload_name, pathlib.Path("/output"), "rw")]
        cmd = stabilize + podman(workload_name, mounts) + no_random + timer + tracer.prefix + stage_cmd
        print(f"Running {tracer_name} {workload_name}")
        print(shlex.join(map(str, cmd)))
        subprocess.run(
            cmd,
            check=True,
        )
        ops = tracer.count_ops()
        resources = yaml.load(time_json.read_bytes() if time_json.exists() else "{}", Loader=TupleKeyLoader)
        yield label, resources, ops

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


repetitions = 11
schema = {
    "tracer": polars.Categorical(),
    "workload": polars.Categorical(),
    "stage": polars.Categorical(),
    "iteration": polars.Int8(),
    "wall_time": polars.datatypes.Duration("us"),
    "cpu_time": polars.datatypes.Duration("us"),
    "kernel_time": polars.datatypes.Duration("us"),
    "memory": polars.UInt64(),
    "op_counts": polars.List(polars.Struct({"key": polars.String, "value": polars.UInt32})),
}


def main() -> None:
    if results_file.exists():
        df = polars.read_parquet(results_file)
    else:
        df = polars.DataFrame(
            data={
                "tracer": [],
                "workload": [],
                "stage": [],
                "iteration": [],
                "wall_time": [],
                "cpu_time": [],
                "kernel_time": [],
                "memory": [],
                "op_counts": [],
            },
            schema=schema,
        )

    print("initial")
    print(df)


    trials_done = set(df.select(["tracer", "workload", "iteration"]).rows())
    for it in tqdm.trange(repetitions, desc="trials"):
        trials = set(itertools.product(
            tracers.keys(),
            workloads.keys(),
            (it,),
        ))
        trials_to_do = list(trials - trials_done)
        random.Random(0).shuffle(trials_to_do)
        for tracer_name, workload_name, iteration in trials_to_do:
            for stage, resources, ops in do_trial(tracer_name, workload_name):
                new_row = polars.DataFrame({
                    "tracer": [tracer_name],
                    "workload": [workload_name],
                    "stage": [stage],
                    "iteration": [iteration],
                    "wall_time": [resources["rusage"]["stop"] - resources["rusage"]["start"]],
                    "cpu_time": [resources["rusage"]["cpu_user_us"]],
                    "kernel_time": [resources["rusage"]["cpu_system_us"]],
                    "memory": [resources["rusage"]["peak_memory_usage"]],
                    "op_counts": [[
                        {"key": key, "value": value}
                        for key, value in ops.items()
                    ]],
                }, schema=schema)
                df = df.vstack(new_row)
                df.write_parquet(results_file)
    print("done")
    print(df)


if __name__ == "__main__":
    main()
