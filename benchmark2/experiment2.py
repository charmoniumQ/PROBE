import asyncio
import dataclasses
import json
import pathlib
import shlex
import subprocess
import yaml
from openai_setup import run_model
from openai_setup import InferredProvenance, Rule
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
        obj = asyncio.run(real_infer_provenance(tracer_name, workload_name))
        script_path.parent.mkdir(exist_ok=True, parents=True)
        script_path.write_text(json.dumps(obj, cls=DCJSONEncoder))
        return obj


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

    # Only expose relevant directories to the MCP filesystem server
    top_level_dirs = [str(experiment.sandbox_workload_out), str(experiment.sandbox_tracer_out), "/bin", "/usr", "/etc", "/opt", "/lib"]

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

    return scripts


def load_recorded_provenance(
        workload_name: str,
) -> dict[str, Rule]:
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
    inferred_provs = {}
    paths_of_interest = input_paths | output_paths
    for rule in workflow["rules"]:
        inputs = [str(path) for path in rule["inputs"] if str(path) in paths_of_interest]
        outputs = [str(path) for path in rule["outputs"] if str(path) in paths_of_interest]
        for output in outputs:
            assert output not in inferred_provs
            inferred_provs[output] = Rule(
                output_path=output,
                input_paths=inputs,
                commands_to_reproduce=[rule["command"]],
            )

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
    workload_name = "resnet-tf-mg"
    tracer_name = "rzip"

    inferred = infer_provenance(
        tracer_name,
        workload_name,
    )
    print(inferred.usage)

    recorded_provenance = load_recorded_provenance(workload_name)

    default_rule = Rule(output_path=output, input_paths=[], commands_to_reproduce=[])
    n_inputs_total = 0
    n_inputs_extraneous = 0
    n_inputs_missed = 0
    n_cmds_total = 0
    n_cmds_extraneous = 0
    n_cmds_missed = 0

    n_rules_sound = 0
    n_rules_efficient = 0
    n_rules = 0

    for output, recorded_rule in recorded_provenance.items():
        inferred_rule = inferred.outputs.get(output, default_rule)
        inputs_inferrence_missed = frozenset(recorded_rule.input_paths) - frozenset(inferred_rule.input_paths)
        inputs_inferrence_extraneous = frozenset(inferred_rule.input_paths) - frozenset(recorded_rule.input_paths)
        inputs_inferrence_correct = frozenset(recorded_rule.input_paths) & frozenset(inferred_rule.input_paths)
        cmds_inferrence_missed = frozenset(recorded_rule.commands_to_reproduce) - frozenset(inferred_rule.commands_to_reproduce)
        cmds_inferrence_extraneous = frozenset(inferred_rule.commands_to_reproduce) - frozenset(recorded_rule.commands_to_reproduce)
        cmds_inferrence_correct = frozenset(recorded_rule.commands_to_reproduce) & frozenset(inferred_rule.commands_to_reproduce)

        n_inputs_total += len(recorded_rule.input_paths)
        n_inputs_extraneous += len(inputs_inferrence_extraneous)
        n_inputs_missed += len(inputs_inferrence_missed)
        n_cmds_total += len(recorded_rule.input_paths)
        n_cmds_extraneous += len(cmds_inferrence_extraneous)
        n_cmds_missed += len(cmds_inferrence_missed)

        n_rules += 1

        if not inputs_inferrence_extraneous:
            n_rules_efficient += 1

        if not inputs_inferrence_missed:
            n_rules_sound += 1

        print(output)
        for var, val in dict(
            inputs_inferrence_missed=inputs_inferrence_missed,
            inputs_inferrence_extraneous=inputs_inferrence_extraneous,
            inputs_inferrence_correct=inputs_inferrence_correct,
            cmds_inferrence_missed=cmds_inferrence_missed,
            cmds_inferrence_extraneous=cmds_inferrence_extraneous,
            cmds_inferrence_correct=cmds_inferrence_correct,
        ).items():
            if val:
                print(var, val)

    print(f"{n_inputs_extraneous / n_inputs_total * 100:.0f}% inputs extraneous")
    print(f"{n_inputs_extraneous / n_inputs_total * 100:.0f}% inputs missed")
    print(f"{n_cmds_extraneous / n_cmds_total * 100:.0f}% cmds extraneous")
    print(f"{n_cmds_extraneous / n_cmds_total * 100:.0f}% cmds missed")
    print(f"{n_rules_sound / n_rules * 100:.0f}% rules sound")

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
