import collections.abc
import os
import json
import pprint
import textwrap
import typing
import agents.mcp
import openai
import pydantic


MODEL = "deepseek-v4-flash"


class Output(pydantic.BaseModel):
    output_path: str
    input_paths: list[str]
    commands_to_reproduce: list[list[str]]


class InferredProvenance(pydantic.BaseModel):
    outputs: list[Output]

PROMPT = """
For each of output path:

1. Determine all other output paths and all input paths that may have influenced directly or indirectly to the given output.
2. Write a script that will regenerate the output, assuming input paths and other files are present.

You may use the filesystem.

You may use the shell history in /scratch/shell_history.

The environment variables are in /scratch/env.

You may use the artifact (if any) in /scratch/artifact.

Do not run search_files against /.

Do not attempt to use bash.

Output paths:
{output_paths}

Input paths:
{input_paths}

Use the following JSON schema for your response: {schema}

"""

MAX_TURNS = 70
MCP_TIMEOUT = 120


async def run_model(
        input_paths: list[str],
        output_paths: list[str],
        server_cmd: list[str]
) -> collections.abc.Mapping[str, typing.Any]:
    client = agents.AsyncOpenAI(
        api_key=os.environ.get('DEEPSEEK_API_KEY'),
        base_url="https://api.deepseek.com",
    )
    model = agents.OpenAIChatCompletionsModel(model=MODEL, openai_client=client)
    async with agents.mcp.MCPServerStdio(
        params={
            "command": server_cmd[0],
            "args": server_cmd[1:],
        },
        client_session_timeout_seconds=MCP_TIMEOUT,
        tool_filter=agents.mcp.ToolFilterStatic(
            allowed_tool_names=[
                "read_text_file",
                "read_media_file",
                "read_multiple_files",
                "list_directory",
                "list_directory_with_sizes",
                "search_files",
                "directory_tree",
                "get_file_info",
                "list_allowed_directories",
            ],
        ),
    ) as mcp_file_server:
        agents.set_tracing_disabled(disabled=True)
        agent = agents.Agent(
            name="Assistant",
            model=model,
            mcp_servers=[mcp_file_server],
            model_settings=agents.ModelSettings(
                extra_body={
                    "response_format": {
                        "type": "json_object"
                    }
                }
            ),
        )
        for tool in agent.tools:
            print(tool.name)
        prompt = PROMPT.format(
            output_paths="\n".join(output_paths),
            input_paths="\n".join(input_paths),
            schema=json.dumps(InferredProvenance.model_json_schema()),
        )
        result = agents.Runner.run_streamed(
            agent,
            prompt,
            max_turns=MAX_TURNS,
        )
        async for event in result.stream_events():
            match event:
                case agents.stream_events.AgentUpdatedStreamEvent():
                    pass
                case agents.stream_events.RawResponsesStreamEvent():
                    pass
                case agents.stream_events.RunItemStreamEvent():
                    match event.item:
                        case agents.items.ToolCallItem():
                            print(f"Call {event.item.raw_item.name}({event.item.raw_item.arguments})")
                            print()
                        case agents.items.ToolCallOutputItem():
                            print("ToolCallOutputItem:")
                            # print(textwrap.indent(pprint.pformat(event.item), prefix="    "))
                            output = json.loads(event.item.raw_item["output"])
                            match output["type"]:
                                case "text":
                                    print(f"    len(output['text'])={len(output['text'])}")
                                case _:
                                    print(f"    output['type']={output['type']}")
                            print()
                        case agents.items.MessageOutputItem():
                            first_time = True
                            for subevent in event.item.raw_item.content:
                                if text := getattr(subevent, "text", ""):
                                    if first_time:
                                        print("Message output:")
                                        first_time = False
                                    print(textwrap.indent(text[:100], prefix="    "))
                            print()
                        case agents.items.ReasoningItem():
                            print("Reasoning summary:")
                            for subevent in event.item.raw_item.summary:
                                match subevent:
                                    case openai.types.responses.response_reasoning_item.Summary():
                                        print(textwrap.indent(subevent.text, prefix="    "))
                                    case _:
                                        print(type(subevent))
                            print()
                        case _:
                            print(event.type, type(event), type(event.item), type(event.item.raw_item), "unknown")
                            print("    item=", event.item, sep="")
                            print("    raw_item=", event.item.raw_item, sep="")
                            print()
                case _:
                    print(event.type.__name__, "unknown")
                    print("    attrs=", event.type, type(event), ":", ", ".join(my_dir(event)), sep="")
                    print()

    usage = result.context_wrapper.usage

    # Present for reasoning models
    if hasattr(usage, "output_tokens_details"):
        details = usage.output_tokens_details
        if hasattr(details, "reasoning_tokens"):
            print(f"Reasoning tokens:  {details.reasoning_tokens}")

    obj = InferredProvenance.model_validate_json(result.final_output)
    print("result:", obj)

    return {
        "result": obj,
        "usage": usage,
    }


def my_dir(obj: object) -> list[str]:
    return [attr for attr in dir(obj) if not attr.startswith("_")]
