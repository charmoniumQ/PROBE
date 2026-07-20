import asyncio
import collections.abc
import dataclasses
import json
import pathlib
import shlex
import shutil
import subprocess
import typing
import yaml
# from langchain_setup import run_model
from openai_setup import run_model, InferredProvenance, Output
import experiment


def run_exp(workload_name: str, tracer_name: str) -> None:
    workload = experiment.workloads[workload_name]
    tracer = experiment.tracers[tracer_name]()

    experiment.podman_build(workload.context, workload_name)

    # setup
    (experiment.output_dir / workload_name).mkdir(exist_ok=True)
    mounts = [*workload.mounts, (experiment.output_dir / workload_name, pathlib.Path("/output"), "rw")]
    if workload.setup:
        cmd = experiment.podman(workload_name, mounts) + workload.setup
        print(f"Running {tracer_name} {workload_name} setup")
        print(shlex.join(map(str, cmd)))
        subprocess.run(
            cmd,
            check=True,
        )

    # main run
    cmd = experiment.podman(workload_name, mounts) + tracer.prefix + ["sh", "-c", "set -ex\n" + "\n".join(shlex.join(map(str, cmd)) for _, cmd in workload.run)]
    print(f"Running {tracer_name} {workload_name}")
    print(shlex.join(map(str, cmd)))
    subprocess.run(
        cmd,
        check=True,
    )

    # extract artifact
    cmd = experiment.podman(workload_name, mounts) + tracer.make_artifact
    print(f"Running {tracer_name} {workload_name} artifact")
    print(shlex.join(map(str, cmd)))
    subprocess.run(
        cmd,
        check=True,
    )
    assert tracer.artifact
    initial_artifact_path = experiment.scratch_dir / tracer.artifact
    assert initial_artifact_path.exists()
    final_artifact_path = experiment.results_dir / "artifacts" / tracer_name / workload_name
    final_artifact_path.parent.mkdir(exist_ok=True, parents=True)
    if final_artifact_path.exists():
        final_artifact_path.unlink()
    shutil.move(initial_artifact_path, final_artifact_path)


def get_artifact_path(workload_name: str, tracer_name: str) -> pathlib.Path:
    artifact_path = experiment.results_dir / "artifacts" / tracer_name / workload_name
    if artifact_path.exists():
        return artifact_path
    else:
        run_exp(workload_name, tracer_name)
        assert artifact_path.exists()
        return artifact_path


def llm_infer_prov(
        workload_name: str,
        tracer_name: str,
        workload: experiment.Workload,
        tracer: experiment.ProvTracer,
) -> None:
    if workload.setup:
        cmd = experiment.podman(workload_name, workload.mounts) + workload.setup
        print(f"Running {tracer_name} {workload_name} setup")
        print(shlex.join(map(str, cmd)))
        subprocess.run(
            cmd,
            check=True,
        )
    cmd = experiment.podman(workload_name, workload.mounts) + experiment.join_cmds(*[cmd for _, cmd in workload.run])
    print(f"Running {tracer_name} {workload_name}")
    print(shlex.join(map(str, cmd)))
    subprocess.run(
        cmd,
        check=True,
    )

    assert tracer.make_artifact

    cmd = experiment.podman(workload_name, workload.mounts) + tracer.make_artifact
    print(f"Running {tracer_name} {workload_name} artifact")
    print(shlex.join(map(str, cmd)))
    subprocess.run(
        cmd,
        check=True,
    )
    assert tracer.artifact
    artifact_path = experiment.results_dir / "artifacts" / tracer_name / workload_name
    artifact_path.parent.mkdir(exist_ok=True, parents=True)
    if artifact_path.exists():
        artifact_path.unlink()
    shutil.move(experiment.scratch_dir / tracer.artifact, artifact_path)


async def assess_artifact(
        workload_name: str,
        tracer_name: str,
        artifact_path: pathlib.Path,
) -> collections.abc.Mapping[str, typing.Any]:
    workload = experiment.workloads[workload_name]
    mcp_server_filesystem = experiment.nix_build(".#mcp-server-filesystem") / "bin/mcp-server-filesystem"
    mounts = [*workload.mounts, (experiment.output_dir  / workload_name, pathlib.Path("/output"), "ro")]

    top_level_dirs = subprocess.run(
        args=experiment.podman(workload_name, mounts) + ["sh", "-c", "echo /*/ | xargs --max-args 1 echo"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n")
    top_level_dirs = [dir for dir in top_level_dirs if not dir == "nix/"]
    print(top_level_dirs)

    server_cmd = experiment.podman(workload_name, mounts) + ["sh", "-c", shlex.join([str(mcp_server_filesystem), *top_level_dirs]) + " 2>/dev/null"]

    shutil.rmtree(experiment.scratch_dir)
    experiment.scratch_dir.mkdir()
    (experiment.scratch_dir / "shell_history").write_text("\n".join(shlex.join(map(str, cmd)) for _, cmd in workload.run))
    shutil.copy(artifact_path, experiment.scratch_dir / "artifact")
    (experiment.scratch_dir / "env").write_text(subprocess.run(
        experiment.podman(workload_name, mounts) + ["env"],
        capture_output=True,
        text=True,
    ).stdout)

    input_paths = subprocess.run(
        experiment.podman(workload_name, mounts) + ["sh", "-c", f"echo {' '.join(workload.inputs)} | xargs --max-args 1 echo"],
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n")
    output_paths = subprocess.run(
        experiment.podman(workload_name, mounts) + ["sh", "-c", f"echo {' '.join(workload.outputs)} | xargs --max-args 1 echo"],
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n")

    print(shlex.join(server_cmd))
    for i, path in enumerate(output_paths):
        print("out", i, path)

    for i, path in enumerate(input_paths):
        print("in", i, path)

    assert len(output_paths) < 30
    assert len(input_paths) < 30

    scripts = await run_model(
        input_paths,
        output_paths,
        server_cmd,
    )
    script_path = experiment.results_dir / "scripts" / tracer_name / (workload_name + ".json")
    script_path.parent.mkdir(exist_ok=True, parents=True)
    script_path.write_text(json.dumps(scripts, cls=DCJSONEncoder))

    return scripts


def get_correct_prov(
        workload_name: str,
) -> InferredProvenance:
    workload = experiment.workloads[workload_name]
    mounts = [*workload.mounts, (experiment.output_dir  / workload_name, pathlib.Path("/output"), "ro")]

    # Get input/output paths
    input_paths = set(subprocess.run(
        experiment.podman(workload_name, mounts) + ["sh", "-c", f"echo {' '.join(workload.inputs)} | xargs --max-args 1 echo"],
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n"))
    output_paths = set(subprocess.run(
        experiment.podman(workload_name, mounts) + ["sh", "-c", f"echo {' '.join(workload.outputs)} | xargs --max-args 1 echo"],
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n"))

    # Parse graph
    artifact_path = get_artifact_path(workload_name, "probe-slow")
    workflow = yaml.safe_load(artifact_path.read_text())
    inferred_provs = []
    paths_of_interest = input_paths | output_paths
    for rule in workflow["rules"]:
        inputs = [str(path) for path in rule["inputs"] if str(path) in paths_of_interest]
        outputs = [str(path) for path in rule["outputs"] if str(path) in paths_of_interest]
        for output in outputs:
            inferred_provs.append(Output(
                output_path=output,
                input_paths=inputs,
                commands_to_reproduce=[rule["command"]],
            ))
    return InferredProvenance(outputs=inferred_provs)


def rewrite_with_mounts(path: pathlib.Path, mounts: list[tuple[pathlib.Path, pathlib.Path, str]]) -> pathlib.Path:
    for src, dst, _ in mounts:
        if path.is_relative_to(src):
            return dst / path.relative_to(src)
    return path


class DCJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        elif hasattr(o, "model_dump"):
            return o.model_dump()
        return super().default(o)


if __name__ == "__main__":
    workload_name = "torch-attention"
    tracer_name = "none"
    scripts = asyncio.run(assess_artifact(
        workload_name,
        tracer_name,
        get_artifact_path(workload_name, tracer_name)
    ))
    # for output in get_correct_prov(workload_name).outputs:
    #     print(output.output_path)
    #     for input_path in output.input_paths:
    #         print("  " + input_path)
    #     for command in output.commands_to_reproduce:
    #         print(shlex.join(command))
    #     print()

    # tracers = experiment.tracers.keys() - {"probe-fast"}
    # for workload_name, tracer_name in itertools.product(experiment.workloads.keys(), tracers):
    #     workload = experiment.workloads[workload_name]
    #     tracer = experiment.tracers[tracer_name]()
    #     artifact_path = experiment.results_dir / "artifacts" / tracer_name / workload_name
    #     if tracer.make_artifact and not artifact_path.exists():
    #         do_run(workload, tracer)
    #     script_path = experiment.results_dir / "scripts" / tracer_name / workload_name
    #     if not script_path.exists():
    #         scripts = asyncio.run(assess_artifact(workload_name, workload, artifact_path))
    #         script_path.write_text(json.dumps(scripts))
