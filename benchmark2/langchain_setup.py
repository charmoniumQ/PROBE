import asyncio
import dataclasses
import collections.abc
import pprint
import typing

import langchain.agents
import langchain_core.messages.ai
import langchain_mcp_adapters.client


MODEL = "deepseek-v4-flash"


@dataclasses.dataclass
class Output:
    output_path: str
    input_paths: list[str]
    commands_to_reproduce: list[list[str]]


@dataclasses.dataclass
class InferredProvenance:
    outputs: list[Output]


async def run_model(
        input_paths: list[str],
        output_paths: list[str],
        server_cmd: list[str],
) -> collections.abc.Mapping[str, typing.Any]:
    client = langchain_mcp_adapters.client.MultiServerMCPClient(
        {
            "filesystem": {
                "transport": "stdio",
                "command": server_cmd[0],
                "args": server_cmd[1:],
            }
        }
    )
    tools = await client.get_tools()
    tools = [tool for tool in tools if "write" not in tool.name and "edit" not in tool.name and "create" not in tool.name and "move" not in tool.name]
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

    return {
        "output": output["structured_response"],
        "usage_metadata": usage_metadata,
    }
