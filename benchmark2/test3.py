import json
import textwrap
import os
import asyncio
import shlex
import agents.mcp
import openai.types.responses


MODEL = "deepseek-v4-flash"


async def main() -> None:
    cmd = [
        # "podman",
        # "run",
        # "--volume=/nix/store:/nix/store:ro",
        # "--volume=/home/sam/box/PROBE/.cache:/scratch:rw",
        # "--volume=/home/sam/.cache/cargo-builds/debug:/home/sam/.cache/cargo-builds/debug:ro",
        # "--volume=/home/sam/box/PROBE/benchmark2/resnet-tf-mg/scripts:/scripts:ro",
        # "--rm",
        # "--interactive",
        # "resnet-tf-mg",

        # "sh",
        # "-c",
        # shlex.join([

            "/nix/store/xm7q9hcw4hrgbnh8a950v73yr9p9jzcv-mcp-server-filesystem-2026.1.26/bin/mcp-server-filesystem",
            "/",

        # ])
        # + " 2>/dev/null",
    ]
    print(shlex.join(cmd))
    client = agents.AsyncOpenAI(
        api_key=os.environ.get('DEEPSEEK_API_KEY'),
        base_url="https://api.deepseek.com",
    )
    model = agents.OpenAIChatCompletionsModel(model=MODEL, openai_client=client)
    async with agents.mcp.MCPServerStdio(
        params={
            "command": cmd[0],
            "args": cmd[1:],
        },
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
        agent = agents.Agent(
            name="Assistant",
            model=model,
            mcp_servers=[mcp_file_server],
        )
        result = agents.Runner.run_streamed(agent, "Find the version of Python that is used")
        async for event in result.stream_events():
            match event:
                case agents.stream_events.AgentUpdatedStreamEvent():
                    pass
                case agents.stream_events.RawResponsesStreamEvent():
                    # match event.data:
                    #     case openai.types.responses.ResponseCreatedEvent():
                    #         pass
                    #     case openai.types.responses.ResponseOutputItemAddedEvent():
                    #         pass
                    #     case openai.types.responses.ResponseReasoningSummaryPartAddedEvent():
                    #         pass
                    #     case openai.types.responses.ResponseReasoningSummaryTextDeltaEvent():
                    #         pass
                    #     case openai.types.responses.ResponseContentPartAddedEvent():
                    #         pass
                    #     case openai.types.responses.ResponseContentPartDoneEvent():
                    #         pass
                    #     case openai.types.responses.ResponseTextDeltaEvent():
                    #         pass
                    #     case openai.types.responses.ResponseReasoningSummaryPartDoneEvent():
                    #         print(event.type, type(event), type(event.data))
                    #         print("    part=", getattr(event.data, "part", None), sep="")
                    #         print()
                    #     case openai.types.responses.ResponseOutputItemDoneEvent():
                    #         match event.data.item:
                    #             case openai.types.responses.ResponseReasoningItem():
                    #                 print(event.type, type(event), type(event.data), type(event.data.item))
                    #                 print("    summary=", event.data.item.summary, sep="")
                    #                 print()
                    #             case openai.types.responses.ResponseFunctionToolCall():
                    #                 print(event.type, type(event), type(event.data), type(event.data.item))
                    #                 print("    arguments=", event.data.item.arguments, sep="")
                    #                 print()
                    #             case openai.types.responses.ResponseOutputMessage():
                    #                 pass
                    #             case _:
                    #                 print(event.type, type(event), type(event.data), type(event.data.item), "unknown")
                    #                 print("   ", event.data.item)
                    #                 print()
                    #     case openai.types.responses.ResponseCompletedEvent():
                    #         print(event.type, type(event), type(event.data))
                    #         for i, subevent in enumerate(event.data.response.output):
                    #             match subevent:
                    #                 case openai.types.responses.ResponseReasoningItem():
                    #                     print(f"    [{i}].summary=", subevent.summary, sep="")
                    #                 case openai.types.responses.ResponseOutputMessage():
                    #                     pass
                    #                 case openai.types.responses.ResponseFunctionToolCall():
                    #                     print(f"    [{i}].arguments=", subevent.arguments, sep="")
                    #                 case _:
                    #                     print("   ", event.type, type(event), type(event.data), type(subevent), "unknown")
                    #                     print(f"    [{i}]=", subevent, sep="")
                    #         print("    usage=", event.data.response.usage, sep="")
                    #         print()
                    #     case openai.types.responses.ResponseFunctionCallArgumentsDeltaEvent():
                    #         pass
                    #         # print(event.type, type(event), type(event.data))
                    #         # print(textwrap.indent(event.data.to_json(), prefix="    "))
                    #     case _:
                    #         print(event.type, type(event), type(event.data), "unknown")
                    #         print("    attrs=", ", ".join(my_dir(event.data)), sep="")
                    #         print()
                    pass
                case agents.stream_events.RunItemStreamEvent():
                    match event.item:
                        case agents.items.ToolCallItem():
                            print(event.type, type(event), type(event.item), type(event.item.raw_item))
                            print("    arguments=", event.item.raw_item.arguments, sep="")
                            print()
                        case agents.items.ToolCallOutputItem():
                            # print(event.type, type(event), type(event.item), type(event.item.raw_item))
                            # print("    output=", event.item.raw_item["output"], sep="")
                            # print()
                            pass
                        case agents.items.MessageOutputItem():
                            print(event.type, type(event), type(event.item), type(event.item.raw_item))
                            print("    content=", event.item.raw_item.content, sep="")
                            print()
                        case agents.items.ReasoningItem():
                            print(event.type, type(event), type(event.item), type(event.item.raw_item))
                            print("    summary=", event.item.raw_item.summary, sep="")
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

        response = result.get_final_response()

    print("\n\nFinal answer:")
    print(response.output_text)


def my_dir(obj: object) -> list[str]:
    return [attr for attr in dir(obj) if not attr.startswith("_")]


asyncio.run(main())

# print("\n=== Usage ===")
# print(f"Input tokens:      {usage.input_tokens}")
# print(f"Output tokens:     {usage.output_tokens}")
# print(f"Total tokens:      {usage.total_tokens}")

# # Present for reasoning models
# if hasattr(usage, "output_tokens_details"):
#     details = usage.output_tokens_details
#     if hasattr(details, "reasoning_tokens"):
#         print(f"Reasoning tokens:  {details.reasoning_tokens}")
