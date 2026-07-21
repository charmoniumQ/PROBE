import asyncio
import dataclasses
import json
import pathlib
import shlex
import subprocess
import yaml
from openai_setup import run_model
from openai_setup import InferredProvenance, Output
import experiment


inferred_prov_path = experiment.results_dir / "inferred_prov"
inferred_prov_path.mkdir(exist_ok=True)


def infer_provenance(
        tracer_name: str,
        workload_name: str,
) -> InferredProvenance:
    script_path = inferred_prov_path / f"{tracer_name}-{workload_name}.json"
    if script_path.exists():
        return InferredProvenance.model_validate_json(script_path.read_text())
    else:
        return asyncio.run(real_infer_provenance(tracer_name, workload_name))


async def real_infer_provenance(
        tracer_name: str,
        workload_name: str,
) -> InferredProvenance:
    workload = experiment.workloads[workload_name]
    mcp_server_filesystem = experiment.nix_build(".#mcp-server-filesystem") / "bin/mcp-server-filesystem"
    tracer_output_dir, workload_output_dir, mounts = experiment.get_mounts(tracer_name, workload_name, False)

    if not list(workload_output_dir.iterdir()):
        experiment.do_trial(tracer_name, workload_name, True, True, True)
        assert list(workload_output_dir.iterdir())

    top_level_dirs = subprocess.run(
        args=experiment.podman(workload_name, mounts) + ["sh", "-c", "echo /*/ | xargs --max-args 1 echo"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n")
    top_level_dirs = [dir for dir in top_level_dirs if not dir == "nix/"]

    server_cmd = experiment.podman(workload_name, mounts) + ["sh", "-c", shlex.join([str(mcp_server_filesystem), *top_level_dirs]) + " 2>/dev/null"]

    (tracer_output_dir / "shell_history").write_text("\n".join(shlex.join(map(str, cmd)) for _, cmd in workload.run))
    (tracer_output_dir / "env").write_text(subprocess.run(
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

    tracer = experiment.tracers[tracer_name]()

    scripts = await run_model(
        input_paths,
        output_paths,
        server_cmd,
        tracer_name,
        tracer_output_dir / tracer.artifact,
    )
    script_path = inferred_prov_path / f"{tracer_name}-{workload_name}.json"
    script_path.parent.mkdir(exist_ok=True, parents=True)
    script_path.write_text(json.dumps(scripts, cls=DCJSONEncoder))

    return scripts


def load_recorded_provenance(
        workload_name: str,
) -> list[Output]:
    workload = experiment.workloads[workload_name]
    this_tracer_out, _, mounts = experiment.get_mounts("probe-slow", workload_name, False)

    # Parse graph
    if not this_tracer_out.exists():
        experiment.do_trial("probe-slow", workload_name, True, True, True)

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

    workflow = yaml.safe_load(this_tracer_out.read_text())
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

    return inferred_provs


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
    workload_name = "simple"
    tracer_name = "none"

    scripts = infer_provenance(
        tracer_name,
        workload_name,
    )

    # for output in load_recorded_provenance(workload_name):
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
