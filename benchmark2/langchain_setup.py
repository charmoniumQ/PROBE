import collections.abc
import pathlib
import pprint
import textwrap
import typing

import experiment
import langchain_core.language_models
import langchain_deepseek
import langchain_mcp_adapters.client
import langchain.agents

from openai_setup import InferredProvenance, MODEL, PROMPT, SCHEMA


async def run_model(
        input_paths: list[str],
        output_paths: list[str],
        server_cmd: list[str],
        tracer_name: str,
        tracer_artifact: pathlib.Path,
) -> InferredProvenance:
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
    model = langchain_deepseek.ChatDeepSeek(model=MODEL, temperature=0)

    agent = langchain.agents.create_agent(
        model,
        tools,
    )
    
    input = {
        "messages": [
            {
                "role": "user",
                "content": PROMPT.format(
                    output_paths="\n".join(output_paths),
                    input_paths="\n".join(input_paths),
                    tracer_output=str(experiment.sandbox_tracer_out),
                    schema=SCHEMA,
                    tracer_name=tracer_name,
                    tracer_artifact=tracer_artifact,
                ),
            }
        ]
    }
    async with await agent.astream_events(
        input=input,
        version="v3"
    ) as stream:
        limit = 500

        async for message in stream.messages:
            if text := await message.text:
                print("text")
                print(textwrap.indent(text[:limit], prefix="  "))
                print()

            if reasoning := await message.reasoning:
                print("reasoning")
                print(textwrap.indent(reasoning[:limit], prefix="  "))
                print()

            if calls := await message.tool_calls:
                for call in calls:
                    print(f"tool {call['name']}({call.get('args')})")
                    if info := remove_keys(call, {"name", "args", "id", "type"}):
                        print(textwrap.indent(pprint.pformat(info)[:limit], prefix="  "))
                    print()

            if output := message.output_message:
                for message in output.content:
                    match message["type"]:
                        case "reasoning" | "text" | "tool_call":
                            pass
                        case _:
                            print("output_message")
                            print(textwrap.indent(pprint.pformat(message)[:limit], prefix="  "))
                            print()

        result = await stream.output()
        print("result")
        print(textwrap.indent(pprint.pformat(result["messages"][-1]), prefix="  "))
        print()

        print(type(message))
    print()

    return InferredProvenance.model_validate(dict(
        output=[],
        usage={},
    ))


_K = typing.TypeVar("_K")
_V = typing.TypeVar("_V")


def remove_keys(dct: collections.abc.Mapping[_K, _V], keys: collections.abc.Container[_K]) -> collections.abc.Mapping[_K, _V]:
    return {key: val for key, val in dct.items() if key not in keys}
