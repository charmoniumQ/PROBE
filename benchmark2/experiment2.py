import asyncio
import collections.abc
import dataclasses
import json
import pathlib
import pprint
import random
import shlex
import shutil
import subprocess
import typing

import langchain.agents
import langchain_core.messages.ai
import langchain_mcp_adapters.client

import experiment


def do_run(
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


MODEL = "deepseek-chat"


@dataclasses.dataclass
class Output:
    output_path: str
    input_paths: list[str]
    commands_to_reproduce: list[list[str]]


@dataclasses.dataclass
class InferredProvenance:
    outputs: list[Output]


async def assess_artifact(
        workload_name: str,
        artifact_path: pathlib.Path,
) -> tuple[InferredProvenance, collections.abc.Mapping[str, typing.Any]]:
    workload = experiment.workloads["resnet-tf-mg"]
    mcp_server_filesystem = experiment.nix_build(".#mcp-server-filesystem") / "bin/mcp-server-filesystem"
    mounts = [*workload.mounts, (experiment.output_dir  / workload_name, pathlib.Path("/output"), "ro")]
    server_cmd = experiment.podman(workload_name, mounts) + [str(mcp_server_filesystem), "/"]
    client = langchain_mcp_adapters.client.MultiServerMCPClient(
        {
            "filesystem": {
                "transport": "stdio",
                "command": "sh",
                "args": ["-c", shlex.join(server_cmd) + " 2>/dev/null"],
            }
        }
    )
    tools = await client.get_tools()
    tools = [tool for tool in tools if "write" not in tool.name and "edit" not in tool.name and "create" not in tool.name and "move" not in tool.name]
    shell_history = "\n".join(shlex.join(map(str, cmd)) for _, cmd in workload.run)
    shutil.rmtree(experiment.scratch_dir)
    experiment.scratch_dir.mkdir()
    (experiment.scratch_dir / "shell_history").write_text(shell_history)
    shutil.copy(artifact_path, experiment.scratch_dir / "artifact")

    output_paths = subprocess.run(
        experiment.podman(workload_name, mounts) + ["sh", "-c", f"echo {' '.join(workload.outputs)} | xargs --max-args 1 echo"],
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n")

    input_paths = subprocess.run(
        experiment.podman(workload_name, mounts) + ["sh", "-c", f"echo {' '.join(workload.inputs)} | xargs --max-args 1 echo"],
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n")

    for i, path in enumerate(output_paths):
        print("out", i, path)

    for i, path in enumerate(input_paths):
        print("in", i, path)

    assert len(output_paths) < 50
    agent = langchain.agents.create_agent(MODEL, tools, response_format=InferredProvenance)
    input = {
        "messages": [
            {
                "role": "user",
                "content": f"""
For each of output path:

1. Determine all other output paths and all input paths that may have influenced directly or indirectly to the given output.
2. Write a script that will regenerate the output from scratch.

You may use the filesystem.

You may use the shell history in /scratch/shell_history.

You may use the artifact (if any) in /scratch/artifact.

Output paths:
{'\n'.join(map(str, output_paths))}

Input paths:
{'\n'.join(map(str, input_paths))} 
                    """,
            }
        ]
    }
    print(input["messages"][0]["content"])
    usage_metadata = {}
    async with await agent.astream_events(
        input=input,
        version="v3"
    ) as stream:
        limit = 200

        async def print_tool_calls() -> None:
            async for call in stream.tool_calls:
                print("tool input:", pprint.pformat(call.input)[:limit])
                if output := call.output:
                    output2 = await output
                    print("tool output:", pprint.pformat(output2)[:limit])

        async def print_messages() -> None:
            async for message in stream.messages:
                text = await message.text
                print("text", text)

                reasoning = await message.reasoning
                print("reasoning", reasoning)

                final = await message.output

                if final.usage_metadata:
                    print("final text:", final.text)
                    print("final usage:", final.usage_metadata)
                    print("final.pretty:", final.pretty_print())
                    usage_metadata.update(final.usage_metadata)

        _, _, output = await asyncio.gather(print_tool_calls(), print_messages(), stream.output())

    return output["structured_response"], usage_metadata


def rewrite_with_mounts(path: pathlib.Path, mounts: list[tuple[pathlib.Path, pathlib.Path, str]]) -> pathlib.Path:
    for src, dst, _ in mounts:
        if path.is_relative_to(src):
            return dst / path.relative_to(src)
    return path



class DCJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


if __name__ == "__main__":
    workload = "resnet-tf-mg"
    tracer = "none"
    blank_artifact = pathlib.Path("blank_artifact")
    blank_artifact.write_text("")
    script_path = experiment.results_dir / "scripts" / tracer / (workload + ".json")
    scripts = asyncio.run(assess_artifact(
        "resnet-tf-mg",
        blank_artifact
    ))
    script_path.parent.mkdir(exist_ok=True, parents=True)
    script_path.write_text(json.dumps(scripts, cls=DCJSONEncoder))
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
