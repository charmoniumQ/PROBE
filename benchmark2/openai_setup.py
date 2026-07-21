import os
import json
import re
import pathlib
import pprint
import textwrap
import typing
import agents.mcp
import openai
import pydantic
import experiment


MODEL = "deepseek-v4-flash"


class Rule(pydantic.BaseModel):
    output_path: str
    input_paths: list[str]
    commands_to_reproduce: list[list[str]]


class Outputs(pydantic.BaseModel):
    outputs: dict[str, Rule]


class InferredProvenance(pydantic.BaseModel):
    outputs: dict[str, Rule]
    usage: dict[str, typing.Any]


PROMPT = """
For each output path below, determine which input paths influenced it and write a script that regenerates it.

You may use the filesystem tools to examine:
- Shell history at /{tracer_output}/shell_history
- Environment variables at /{tracer_output}/env
- The {tracer_name} artifact at /{tracer_output}/{tracer_artifact!s}
- Output files and input files

Once you have gathered enough information (typically within 5-10 tool calls), produce your final answer as a single JSON object matching this schema: {schema}

Output paths:
{output_paths}

Input paths:
{input_paths}

"""

MAX_TURNS = 100
MCP_TIMEOUT = 120

SCHEMA = json.dumps(Outputs.model_json_schema())


async def run_model(
        input_paths: list[str],
        output_paths: list[str],
        server_cmd: list[str],
        tracer_name: str,
        tracer_artifact: pathlib.Path,
) -> InferredProvenance:
    client = agents.AsyncOpenAI(
        api_key=os.environ.get('DEEPSEEK_API_KEY'),
        base_url="https://api.deepseek.com",
    )
    model = agents.OpenAIChatCompletionsModel(model=MODEL, openai_client=client, buffer_streamed_tool_calls=True)
    async with agents.mcp.MCPServerStdio(
        params={
            "command": server_cmd[0],
            "args": server_cmd[1:],
        },
        client_session_timeout_seconds=MCP_TIMEOUT,
        tool_filter=agents.mcp.ToolFilterStatic(
            allowed_tool_names=[
                "read_text_file",
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
            instructions="You are a build provenance analyzer. Your task is to determine the input files and commands needed to reproduce each output file. Use the filesystem tools to gather information, then produce your final answer as a JSON object matching the requested schema. Once you have sufficient information, stop making tool calls and output the JSON immediately.",
            mcp_servers=[mcp_file_server],
            model_settings=agents.ModelSettings(),
        )
        for tool in agent.tools:
            print(tool.name)
        prompt = PROMPT.format(
            output_paths="\n".join(output_paths),
            input_paths="\n".join(input_paths),
            schema=SCHEMA,
            tracer_output=str(experiment.sandbox_tracer_out),
            tracer_name=tracer_name,
            tracer_artifact=tracer_artifact,
        )
        result = agents.Runner.run_streamed(
            agent,
            prompt,
            max_turns=MAX_TURNS,
        )
        all_message_text = []
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
                            raw_output = event.item.raw_item.get("output", event.item.raw_item.get("raw_output", ""))
                            if isinstance(raw_output, str):
                                print(f"    len(output)={len(raw_output)}")
                            elif isinstance(raw_output, list):
                                for i, output in enumerate(raw_output):
                                    if isinstance(output, dict):
                                        match output.get("type"):
                                            case "text" | "input_text":
                                                print(f"    [{i}] text: len={len(output.get('text', ''))}")
                                            case _:
                                                print(f"    [{i}] type={output.get('type')}")
                                    elif isinstance(output, str):
                                        print(f"    [{i}] len(str)={len(output)}")
                                    else:
                                        print(f"    [{i}] type={type(output).__name__}")
                            elif isinstance(raw_output, dict):
                                for key, val in raw_output.items():
                                    if isinstance(val, str):
                                        print(f"    {key}: len={len(val)}")
                                    else:
                                        print(f"    {key}: {pprint.pformat(val)}")
                            else:
                                print(f"    type={type(raw_output).__name__}")
                            print()
                        case agents.items.MessageOutputItem():
                            first_time = True
                            for subevent in event.item.raw_item.content:
                                if text := getattr(subevent, "text", ""):
                                    all_message_text.append(text)
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

    if hasattr(usage, "output_tokens_details"):
        details = usage.output_tokens_details
        if hasattr(details, "reasoning_tokens"):
            print(f"Reasoning tokens:  {details.reasoning_tokens}")

    full_text = "".join(all_message_text)
    json_match = re.search(r'\{[\s\S]*\}', full_text)
    final_output = json_match.group(0) if json_match else (result.final_output or "")

    final_output = final_output.strip()
    final_output = re.sub(r'^```(?:json)?\s*\n', '', final_output)
    final_output = re.sub(r'\n```\s*$', '', final_output)

    return InferredProvenance(
        outputs=Outputs.model_validate(
            json.loads(final_output) if isinstance(final_output, str) else final_output
        ).outputs,
        usage={
            "requests": usage.requests,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
        },
    )


def my_dir(obj: object) -> list[str]:
    return [attr for attr in dir(obj) if not attr.startswith("_")]
