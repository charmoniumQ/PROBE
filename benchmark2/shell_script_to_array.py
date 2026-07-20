import json
import collections.abc
import shlex
import pathlib

def parse_shell_script(text: str) -> list[list[str]]:
    """Parse a shell script into a list of argument lists."""
    commands = []
    vars = dict[str, str]()

    for line in text.splitlines():
        line = line.strip()

        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        lexer = shlex.shlex(line, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"

        if "=" in line:
            var, _, val = line.partition("=")
            vars[var] = replace_vars(vars, val).replace('"', "")
            print("---", var, val, vars[var])
        else:
            args = [
                replace_vars(vars, arg)
                for arg in lexer
            ]
            if "|" in args or "<" in args or ">" in args:
                commands.append([
                    "sh",
                    "-c",
                    shlex.join(args).replace("'|'", "|").replace("'<'", "<").replace("'>'", ">"),
                ])
            else:
                commands.append(args)

    return commands


def replace_vars(vars: collections.abc.Mapping[str, str], arg: str) -> str:
    for var, val in vars.items():
        arg = arg.replace("$" + var, val)
    return arg


cmds = []
for cmd in parse_shell_script(pathlib.Path("torch_attention/run2.sh").read_text()):
    print(shlex.join(cmd))
    cmds.append(cmd)
print(json.dumps(cmds))
