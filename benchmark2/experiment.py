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


def join_cmds(*cmds: list[str]) -> list[str]:
    return [
        "sh",
        "-c",
        " && ".join(shlex.join(map(str, cmd)) for cmd in cmds),
    ]


project_root = pathlib.Path(__file__).resolve().parent.parent


@functools.lru_cache
def nix_build(buildable: str) -> pathlib.Path:
    print(f"Building: {buildable}")
    cmd = ["nix", "build", buildable, "--print-out-paths", "--show-trace"]
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=project_root,
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
    setup: list[str]
    run: list[tuple[str, list[str]]]
    context: pathlib.Path
    mounts: list[tuple[pathlib.Path, pathlib.Path, str]]
    inputs: list[str]
    outputs: list[str]


@dataclasses.dataclass
class ProvTracer:
    prefix: list[str]
    make_artifact: list[str]
    artifact: pathlib.Path
    count_ops: typing.Callable[[pathlib.Path], collections.abc.Mapping[str, int]]


root_dir = pathlib.Path(__file__).resolve().parent.parent.resolve()
results_dir = root_dir / ".results"
results_dir.mkdir(exist_ok=True)
results_file = results_dir / "db.parquet"
host_workload_out = root_dir / ".results" / "workload"
host_workload_out.mkdir(exist_ok=True)
host_tracer_out = root_dir / ".results" / "tracer"
host_tracer_out.mkdir(exist_ok=True)
host_timer_out = root_dir / ".results" / "timer"
host_timer_out.mkdir(exist_ok=True)
host_setup_out = root_dir / ".results" / "setup"
host_setup_out.mkdir(exist_ok=True)
sandbox_workload_out = pathlib.Path("/workload_output")
sandbox_tracer_out = pathlib.Path("/tracer_output")
sandbox_timer_out = pathlib.Path("/timer_output")
sandbox_setup_out = pathlib.Path("/setup")
host_tracer_out.mkdir(exist_ok=True)
cpus = [1]
ncpus = 1
benchmark_utils = pathlib.Path("~/.cache/cargo-builds/debug").expanduser()


stabilize = [
    str(benchmark_utils / "systemd-stabilize"),
    "--reserved-cpus=0",
    # f"--reserved-memory={1024*1024*1024}",
    "--",
    str(benchmark_utils / "host-stabilize"),
    "--disable-aslr",
    "--reserved-cpus=0",
    "--disable-smt",
    "--disable-freq-scaling",
    "--drop-fs-cache",
    "--",
]


def podman(image: str, mounts: list[tuple[pathlib.Path, pathlib.Path, str]]) -> list[str]:
    return [
        "podman",
        "run",
        "--volume=/nix/store:/nix/store:ro",
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


no_random = [str(benchmark_utils / "no-random")]


timer = [
    str(benchmark_utils / "process-stabilize"),
    "--repetitions=1",
    # "--key=",
    f"/{sandbox_timer_out}/time.yaml",
    "--",
]


tracers = {
    "none": lambda: ProvTracer(
        [],
        ["sh", "-c", f"echo > {sandbox_tracer_out!s}/blank"],
        pathlib.Path("blank"),
        lambda _: {},
    ),
    "strace": lambda: ProvTracer(
        [
            str(nix_build(".#strace.out") / "bin/strace"),
            "--follow-forks",
            f"--output={sandbox_tracer_out!s}/strace.log"
        ],
        [
            "true",
        ],
        pathlib.Path("strace.log"),
        strace_counts,
    ),
    "probe-fast": lambda: ProvTracer(
        [
            str(nix_build(".#probe") / "bin/probe"),
            "record",
            "--copy-files=none",
            "--no-transcribe",
            "--overwrite",
        ],
        [
            "sh",
            "-c",
            f"echo > {sandbox_tracer_out!s}/artifact",
        ],
        pathlib.Path("artifact"),
        lambda _: {},
    ),
    # "probe-slow": lambda: ProvTracer(
    #     [
    #         str(nix_build(".#probe") / "bin/probe"),
    #         "record",
    #         "--copy-files=eagerly",
    #         f"--output={sandbox_tracer_out!s}/probe_log",
    #         "--overwrite",
    #     ],
    #     [
    #         str(nix_build(".#probe") / "bin/probe"),
    #         "py",
    #         "export",
    #         "workflow",
    #         f"--probe-log={sandbox_tracer_out!s}/probe_log",
    #         "/*",
    #         "--loose",
    #         f"--output={sandbox_tracer_out!s}/workflow.yaml",
    #     ],
    #     pathlib.Path("workflow.yaml"),
    #     probe_counts,
    # ),
    "ptu": lambda: ProvTracer(
        [
            str(nix_build(".#provenance-to-use-dir") / "bin/ptu"),
            f"{sandbox_tracer_out!s}/cde-package",
        ],
        ["true"],
        pathlib.Path("cde-package/provenance.cde-root.1.log"),
        ptu_counts,
    ),
    "rzip": lambda: ProvTracer(
        [
            str(nix_build(".#reprozip") / "bin/reprozip"),
            "trace",
            "--overwrite",
            f"--dir={sandbox_tracer_out!s}/rpz",
        ],
        join_cmds(
            ["rm", "--force", f"{sandbox_tracer_out!s}/provenance.dot"],
            [
                str(nix_build(".#reprounzip") / "bin/reprounzip"),
                "graph",
                f"{sandbox_tracer_out!s}/provenance.dot",
                f"--dir={sandbox_tracer_out!s}/rpz",
            ]
        ),
        pathlib.Path("provenance.dot"),
        reprozip_counts,
    ),
}


def probe_counts(this_host_tracer_out: pathlib.Path) -> collections.abc.Mapping[str, int]:
    proc = subprocess.run(
        ["probe", "py", "op-counts", "--probe-log", str(this_host_tracer_out / "probe_log")],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout.strip().split("\n")[-1])


def strace_counts(this_host_tracer_out: pathlib.Path) -> collections.abc.Mapping[str, int]:
    line_regex = re.compile(r"^(?P<pid>\d+) +(?P<op>.+?)\(")
    pids = set()
    ops = collections.Counter[str]()
    for line in (this_host_tracer_out / "strace.log").read_text().split("\n"):
        if match := line_regex.match(line):
            pids.add(int(match.group("pid")))
            ops[match.group("op")[:7]] += 1
    return {**ops, "pids": len(pids)}


def ptu_counts(this_host_tracer_out: pathlib.Path) -> collections.abc.Mapping[str, int]:
    line_regex = re.compile(r"(?P<time>\d+) (?P<pid>\d+) (?P<op>[A-Z]+)")
    pids = set()
    ops = collections.Counter[str]()
    log = this_host_tracer_out / "cde-package/provenance.cde-root.1.log"
    for line in log.read_text().split("\n"):
        if match := line_regex.match(line):
            pids.add(int(match.group("pid")))
            ops[match.group("op")[:7]] += 1
    return {**ops, "pids": len(pids)}


def reprozip_counts(this_host_tracer_out: pathlib.Path) -> collections.abc.Mapping[str, int]:
    db = this_host_tracer_out / "rpz/trace.sqlite3"
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
        setup=["env", "-", "python", "/scripts/10-download.py"],
        run=[
            ("dwnload", ["env", "-", "python", "/scripts/10-download.py"]),
            ("tokenize", ["env", "-", "python", "/scripts/20-tokenizer.py"]),
            ("batch", ["env", "-", "python", "/scripts/25-batch.py"]),
            ("plots", ["env", "-", "python", "/scripts/30-plots.py"]),
            ("build-model", ["env", "-", "python", "/scripts/40-build-transformer.py"]),
            ("train", ["env", "-", "python", "/scripts/50-train.py"]),
            ("inference", ["env", "-", "python", "/scripts/60-inference.py"]),
        ],
        context=root_dir / "benchmark2/resnet-tf-mg/context",
        mounts=[
            (root_dir / "benchmark2/resnet-tf-mg/scripts", pathlib.Path("/scripts"), "ro")
        ],
        outputs=[
            f"{sandbox_workload_out}/trained_model.*",
            f"{sandbox_workload_out}/val_batches/*.pb",
            f"{sandbox_workload_out}/train_batches/*.pb",
            f"{sandbox_workload_out}/val_examples/*.pb",
            f"{sandbox_workload_out}/train_examples/*.pb",
            f"{sandbox_workload_out}/token_lengths.png",
            f"{sandbox_setup_out}/ted_hrlr_translate_pt_en_converter_extracted/ted_hrlr_translate_pt_en_converter/saved_model.pb",
            f"{sandbox_setup_out}/ted_hrlr_translate_pt_en_converter.zip",
        ],
        inputs=[
            "/scripts/*.py",
            "/usr/local/lib/python3.11/dist-packages/tensorflow/__init__.py",
        ],
    ),
#     "simple": Workload(
#         setup=["python", "-c", "import pathlib, random\npathlib.Path('/workload_output/test.txt').write_text(''.join(chr(random.randint(0, 127)) for _ in range(1000)))"],
#         run=[
#             ("stage 1", ["python", "-c", f"""
# import pathlib
# pathlib.Path(f"{sandbox_workload_out}/test.txt").read_text()
# pathlib.Path(f"{sandbox_workload_out}/test2.txt").write_text("hi")
# """]),
#             ("stage 2", ["python", "-c", f"""
# import pathlib
# pathlib.Path(f"{sandbox_workload_out}/test2.txt").read_text()
# pathlib.Path(f"{sandbox_workload_out}/test3.txt").write_text("hi")
# """]),
#         ],
#         context=root_dir / "benchmark2/resnet-tf-mg/context",
#         mounts=[],
#         outputs=[
#             f"{sandbox_workload_out}/test*",
#         ],
#         inputs=[
#             "/usr/bin/python",
#         ]
#     ),
    "torch-attention-2": Workload(
        setup=join_cmds(
            ["/venv/bin/python", "/scripts/download_data.py", "--data-dir", f"{sandbox_workload_out}/data"],
            ["/venv/bin/python", "/scripts/download_data.py", "--data-dir", f"{sandbox_workload_out}/data", "--anki", "fra"],
        ),
        run=[
            ("randomize-data-1", ["shuf", "-n", "1000", f"{sandbox_workload_out}/data/eng-fra.txt", "-o", f"{sandbox_workload_out}/data/eng-fra1.txt"]),
            ("randomize-data-2", ["shuf", "-n", "1000", f"{sandbox_workload_out}/data/eng-fra.txt", "-o", f"{sandbox_workload_out}/data/eng-fra2.txt"]),
            ("randomize-data-3", ["shuf", "-n", "100", f"{sandbox_workload_out}/data/eng-fra.txt", "-o", f"{sandbox_workload_out}/data/eng-fra3.txt"]),
            ("randomize-data-4", ["shuf", "-n", "100", f"{sandbox_workload_out}/data/eng-fra.txt", "-o", f"{sandbox_workload_out}/data/eng-fra4.txt"]),
            ("clean-data-1", ["/venv/bin/python", "/scripts/clean_data.py", "--input", f"{sandbox_workload_out}/data/eng-fra1.txt", "--output", f"{sandbox_workload_out}/data/eng-fra1.txt_clean", "--report-dir", f"{sandbox_workload_out}/clean-data", "--lang1", "eng", "--lang2", "fra", "--seed", "1"]),
            ("clean-data-2", ["/venv/bin/python", "/scripts/clean_data.py", "--input", f"{sandbox_workload_out}/data/eng-fra2.txt", "--output", f"{sandbox_workload_out}/data/eng-fra2.txt_clean", "--report-dir", f"{sandbox_workload_out}/clean-data", "--lang1", "eng", "--lang2", "fra", "--seed", "2"]),
            ("clean-data-3", ["/venv/bin/python", "/scripts/clean_data.py", "--input", f"{sandbox_workload_out}/data/eng-fra3.txt", "--output", f"{sandbox_workload_out}/data/eng-fra3.txt_clean", "--normalize", "--report-dir", f"{sandbox_workload_out}/clean-data_final", "--lang1", "eng", "--lang2", "fra", "--seed", "3"]),
            ("clean-data-4", ["/venv/bin/python", "/scripts/clean_data.py", "--input", f"{sandbox_workload_out}/data/eng-fra2.txt", "--output", f"{sandbox_workload_out}/data/eng-fra4.txt_clean", "--normalize", "--report-dir", f"{sandbox_workload_out}/clean-data_november", "--lang1", "eng", "--lang2", "fra", "--seed", "4"]),
            # ("s41", ["/venv/bin/python", "/scripts/verify_datasets.py", f"{sandbox_workload_out}/data/eng-fra2.txt_clean", f"{sandbox_workload_out}/data/eng-fra3.txt_clean", "--max-length", "10", "--seed", "1", "--report-dir", f"{sandbox_workload_out}/verify1"]),
            # ("s42", ["/venv/bin/python", "/scripts/verify_datasets.py", f"{sandbox_workload_out}/data/eng-fra2.txt_clean", f"{sandbox_workload_out}/data/eng-fra3.txt_clean", "--max-length", "1", "--seed", "10", "--report-dir", f"{sandbox_workload_out}/verify2"]),
            # ("s42", ["/venv/bin/python", "/scripts/verify_datasets.py", f"{sandbox_workload_out}/data/eng-fra2.txt_clean", f"{sandbox_workload_out}/data/eng-fra4.txt_clean", "--max-length", "1", "--seed", "10", "--report-dir", f"{sandbox_workload_out}/verify3"]),
            ("s44", ["ls", "-l", f"{sandbox_workload_out}/data/"]),
            ("s44", ["cp", f"{sandbox_workload_out}/data/eng-fra1.txt_clean", f"{sandbox_workload_out}/data/eng-fra.txt"]),
            ("train-1", ["/venv/bin/python", "/scripts/train.py", "--arch", "rnn", "--size", "small", "--epochs", "60", "--batch-size", "64", "--lr", "0.001", "--output-dir", f"{sandbox_workload_out}/train", "--lang1", "eng", "--lang2", "fra", "--data-dir", f"{sandbox_workload_out}/data", "--run-name", "v1"]),
            ("s52", ["cp", f"{sandbox_workload_out}/data/eng-fra2.txt_clean", f"{sandbox_workload_out}/data/eng-fra.txt"]),
            ("train-2", ["/venv/bin/python", "/scripts/train.py", "--arch", "rnn", "--size", "medium", "--epochs", "80", "--batch-size", "64", "--lr", "0.001", "--output-dir", f"{sandbox_workload_out}/train", "--lang1", "eng", "--lang2", "fra", "--data-dir", f"{sandbox_workload_out}/data", "--run-name", "v2"]),
            ("s54", ["cp", f"{sandbox_workload_out}/data/eng-fra2.txt_clean", f"{sandbox_workload_out}/data/eng-fra.txt"]),
            ("train-3", ["/venv/bin/python", "/scripts/train.py", "--arch", "bahdanau", "--size", "medium", "--epochs", "100", "--batch-size", "64", "--lr", "0.001", "--output-dir", f"{sandbox_workload_out}/train", "--lang1", "eng", "--lang2", "fra", "--data-dir", f"{sandbox_workload_out}/data", "--run-name", "v3"]),
            ("s56", ["cp", f"{sandbox_workload_out}/data/eng-fra1.txt_clean", f"{sandbox_workload_out}/data/eng-fra.txt"]),
            ("train-4", ["/venv/bin/python", "/scripts/train.py", "--arch", "bahdanau", "--size", "medium", "--epochs", "120", "--batch-size", "64", "--lr", "0.01", "--output-dir", f"{sandbox_workload_out}/train", "--lang1", "eng", "--lang2", "fra", "--data-dir", f"{sandbox_workload_out}/data", "--run-name", "v4"]),
            ("compare-1", ["/venv/bin/python", "/scripts/compare.py", f"{sandbox_workload_out}/train/run_v1", f"{sandbox_workload_out}/train/run_v2", "--output-dir", f"{sandbox_workload_out}/comparison/a"]),
            ("compare-2", ["/venv/bin/python", "/scripts/compare.py", f"{sandbox_workload_out}/train/run_v1", f"{sandbox_workload_out}/train/run_v3", "--output-dir", f"{sandbox_workload_out}/comparison/b"]),
            ("compare-3", ["/venv/bin/python", "/scripts/compare.py", f"{sandbox_workload_out}/train/run_v1", f"{sandbox_workload_out}/train/run_v4", "--output-dir", f"{sandbox_workload_out}/comparison/c"]),
            ("compare-4", ["/venv/bin/python", "/scripts/compare.py", f"{sandbox_workload_out}/train/run_v2", f"{sandbox_workload_out}/train/run_v3", "--output-dir", f"{sandbox_workload_out}/comparison/d"]),
            ("compare-all", ["/venv/bin/python", "/scripts/compare.py", f"{sandbox_workload_out}/train/run_v1", f"{sandbox_workload_out}/train/run_v2", f"{sandbox_workload_out}/train/run_v3", f"{sandbox_workload_out}/train/run_v4", "--output-dir", f"{sandbox_workload_out}/comparison/all"]),
            # ["mkdir", f"{sandbox_workload_out}/inferrence"],
            # ["sh", "-c", "grep '^> ' /workload_output/train/run_v1/samples.txt | sed 's/^> //' | shuf -n 10 | python evaluate.py --run-dir /workload_output/train/run_v1 --interactive > /workload_output/inferrence/p1"],
            # ["sh", "-c", "grep '^> ' /workload_output/train/run_v1/samples.txt | sed 's/^> //' | shuf -n 100 | python evaluate.py --run-dir /workload_output/train/run_v1 --interactive > /workload_output/inferrence/p2"],
            # ["sh", "-c", "grep '^> ' /workload_output/train/run_v3/samples.txt | sed 's/^> //' | shuf -n 10 | python evaluate.py --run-dir /workload_output/train/run_v3 --interactive > /workload_output/inferrence/p3"],
        ],
        context=root_dir / "benchmark2/torch_attention/context",
        mounts=[
            (root_dir / "benchmark2/torch_attention/scripts", pathlib.Path("/scripts"), "ro"),
        ],
        inputs=[
            "/scripts/*.py",
            "/scripts/*.py",
            "/venv/lib/python3.14/site-packages/torch/__init__.py",
        ],
        outputs=[
            f"{sandbox_workload_out}/data/*",
            f"{sandbox_workload_out}/train/*",
            f"{sandbox_workload_out}/comparison/*",
        ]
    ),
    "exec-heavy": Workload(
        setup=["true"],
        run=[
            ("stage 1", ["sh", "-c", "seq 10000 | xargs --max-args 1 true"]),
        ],
        context=root_dir / "benchmark2/resnet-tf-mg/context",
        mounts=[],
        outputs=[],
        inputs=[
            "/usr/bin/python",
        ]
    ),
    "read-heavy": Workload(
        setup=["python", "-c", "import pathlib; pathlib.Path('/workload_output/test.txt').write_text('a' * 655360)"],
        run=[
            ("stage 1", ["python", "-c", """
import pathlib
for _ in range(10000):
    pathlib.Path('/workload_output/test.txt').read_text()
"""]),
        ],
        context=root_dir / "benchmark2/resnet-tf-mg/context",
        mounts=[],
        outputs=[],
        inputs=[
            "/usr/bin/python",
        ]
    ),
    "no-op": Workload(
        setup=[],
        run=[
            ("true", ["true"]),
        ],
        context=root_dir / "benchmark2/resnet-tf-mg/context",
        mounts=[],
        outputs=[],
        inputs=[],
    ),
}


@functools.lru_cache
def podman_build(context: pathlib.Path, tag: str) -> None:
    subprocess.run(
        ["podman", "build", "--tag", tag, context],
        check=True,
        capture_output=False,
    )


def get_mounts(
        tracer_name: str,
        workload_name: str,
        fresh: bool,
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, list[tuple[pathlib.Path, pathlib.Path, str]]]:
    workload = workloads[workload_name]
    this_host_workload_out = host_workload_out / workload_name
    if fresh and  this_host_workload_out.exists():
            shutil.rmtree(this_host_workload_out)
    this_host_workload_out.mkdir(exist_ok=True)

    this_host_tracer_out = host_tracer_out / f"{tracer_name}-{workload_name}"
    if fresh and this_host_tracer_out.exists():
        shutil.rmtree(this_host_tracer_out)
    this_host_tracer_out.mkdir(exist_ok=True)

    this_host_setup_out = host_setup_out / workload_name
    this_host_setup_out.mkdir(exist_ok=True)

    mounts = [
        *workload.mounts,
        (this_host_workload_out, sandbox_workload_out, "rw"),
        (this_host_setup_out, sandbox_setup_out, "rw"),
        (this_host_tracer_out, sandbox_tracer_out, "rw"),
        (host_timer_out, sandbox_timer_out, "rw"),
    ]
    return this_host_tracer_out, this_host_setup_out, this_host_workload_out, mounts


def do_trial(
        tracer_name: str,
        workload_name: str,
        combine_stages: bool,
        do_prov: bool,
        fresh: bool,
) -> list[tuple[str, collections.abc.Mapping[str, typing.Any], collections.abc.Mapping[str, typing.Any]]]:
    workload = workloads[workload_name]
    tracer = tracers[tracer_name]()

    podman_build(workload.context, workload_name)

    this_host_tracer_out, this_host_setup, _, mounts = get_mounts(tracer_name, workload_name, fresh)

    if workload.setup and not list(this_host_setup.iterdir()):
        cmd = podman(workload_name, mounts) + workload.setup
        print(f"Running {tracer_name} {workload_name} setup")
        print(shlex.join(cmd))
        subprocess.run(
            cmd,
            check=True,
        )

    time_json = host_timer_out / "time.yaml"

    if combine_stages:
        stages = [
            ("all", ["sh", "-c", "set -ex\n" + "\n".join(shlex.join(map(str, cmd)) for _, cmd in workload.run)])
        ]
    else:
        stages = workload.run

    ret = list[tuple[str, collections.abc.Mapping[str, typing.Any], collections.abc.Mapping[str, typing.Any]]]()
    for label, stage_cmd in stages:
        if time_json.exists():
            time_json.unlink()
        cmd = stabilize + podman(workload_name, mounts) + no_random + timer + tracer.prefix + stage_cmd
        print(f"Running {tracer_name} {workload_name} {label}")
        print(shlex.join(cmd))
        subprocess.run(
            cmd,
            check=True,
        )
        ops = tracer.count_ops(this_host_tracer_out)
        resources = yaml.load(time_json.read_bytes() if time_json.exists() else "{}", Loader=TupleKeyLoader)
        ret.append((label, resources, ops))

    if do_prov:
        cmd = podman(workload_name, mounts) + tracer.make_artifact
        print(f"Running {tracer_name} make prov")
        print(shlex.join(cmd))
        subprocess.run(
            cmd,
            check=True,
        )

    return ret


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


repetitions = 10
schema = {
    "tracer": polars.Categorical(),
    "workload": polars.Categorical(),
    "stage": polars.Categorical(),
    "iteration": polars.Int8(),
    "wall_time": polars.datatypes.Duration("us"),
    "user_time": polars.datatypes.Duration("us"),
    "kernel_time": polars.datatypes.Duration("us"),
    "memory": polars.UInt64(),
    "op_counts": polars.List(polars.Struct({"key": polars.String, "value": polars.UInt32})),
}
FRESH = False


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
                "user_time": [],
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
            for stage, resources, ops in do_trial(tracer_name, workload_name, False, False, FRESH):
                new_row = polars.DataFrame({
                    "tracer": [tracer_name],
                    "workload": [workload_name],
                    "stage": [stage],
                    "iteration": [iteration],
                    "wall_time": [resources["rusage"]["stop"] - resources["rusage"]["start"]],
                    "user_time": [resources["rusage"]["cpu_user_us"]],
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
