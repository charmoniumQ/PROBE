import asyncio
import pprint
import shlex
import subprocess
import textwrap
import langchain.agents
import langchain_deepseek
import langchain_mcp_adapters.client
import experiment
from openai_setup import MODEL
from langchain_setup import remove_keys


async def main() -> None:
    top_level_dirs = subprocess.run(
        ["podman", "run", "--rm", "resnet-tf-mg", "sh", "-c", "echo /*/ | xargs --max-args 1 echo"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n")
    top_level_dirs = [dir for dir in top_level_dirs if not dir == "nix/"]
    mcp_server_filesystem = experiment.nix_build(".#mcp-server-filesystem") / "bin/mcp-server-filesystem"
    cmd = [
        "podman",
        "run",
        "--volume=/nix/store:/nix/store:ro",
        "--rm",
        "--interactive",
        "resnet-tf-mg",
        "sh",
        "-c",
        shlex.join([
            str(mcp_server_filesystem),
            "/bin", "/dev", "/etc", "/home", "/lib", "/proc", "/run", "/opt", "/srv", "/sys", "/usr", "/var", "/tmp",
        ]) + " 2>/dev/null",
    ]
    client = langchain_mcp_adapters.client.MultiServerMCPClient(
        {
            "filesystem": {
                "transport": "stdio",
                "command": cmd[0],
                "args": cmd[1:],
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
                    "content": "What version of Python is installed, and where is it located on disk?",
                }
            ]
        }
    limit = 100
    async with await agent.astream_events(input, version="v3") as stream:
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



if __name__ == "__main__":
    asyncio.run(main())
