import dataclasses
import shlex
import pprint
import asyncio
import langchain.agents
import langchain_deepseek
import langchain_mcp_adapters.client


@dataclasses.dataclass
class Output:
    path: str
    version: str


async def main() -> None:
    model = langchain_deepseek.ChatDeepSeek(
        model="deepseek-v4-flash",
        extra_body={"thinking": {"type": "disabled"}},
    )
    cmd = [
        "podman",
        "run",
        "--volume=/nix/store:/nix/store:ro",
        "--volume=/home/sam/box/PROBE/.cache:/scratch:rw",
        "--volume=/home/sam/.cache/cargo-builds/debug:/home/sam/.cache/cargo-builds/debug:ro",
        "--volume=/home/sam/box/PROBE/benchmark2/resnet-tf-mg/scripts:/scripts:ro",
        "--rm",
        "--interactive",
        "resnet-tf-mg",
        "/nix/store/xm7q9hcw4hrgbnh8a950v73yr9p9jzcv-mcp-server-filesystem-2026.1.26/bin/mcp-server-filesystem",
        "/",
    ]
    client = langchain_mcp_adapters.client.MultiServerMCPClient(
        {
            "filesystem": {
                "transport": "stdio",
                "command": "sh",
                "args": ["-c", shlex.join(cmd) + " 2>/dev/null"],
            }
        }
    )
    tools = await client.get_tools()
    tools = [tool for tool in tools if "write" not in tool.name and "edit" not in tool.name and "create" not in tool.name and "move" not in tool.name]
    agent = langchain.agents.create_agent(model, tools, response_format=Output)
    input = {
            "messages": [
                {
                    "role": "user",
                    "content": "What version of Python is installed, and where is it located on disk?",
                }
            ]
        }
    limit = 100
    async with await agent.astream_events(input, version="v3") as stream:
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

        _, _, output = await asyncio.gather(print_tool_calls(), print_messages(), stream.output())



if __name__ == "__main__":
    asyncio.run(main())
