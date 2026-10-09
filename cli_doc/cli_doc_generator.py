"""Regenerate ``cli_doc/README.md`` from the current ``probe`` CLI."""

import dataclasses
import subprocess
from pathlib import Path

import click
import probe_py.cli
import typer.main

README = Path(__file__).resolve().parent / "README.md"

_BOILERPLATE_FLAGS = ("--help", "--version")


@dataclasses.dataclass(frozen=True)
class Param:
    syntax: str
    description: str


@dataclasses.dataclass(frozen=True)
class Command:
    name: str
    summary: str
    params: list[Param]


def run(*args: str) -> str:
    """Run *args* and return its standard output."""
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def split_clap_columns(line: str) -> tuple[str, str]:
    """Split a clap help row into its option and description columns."""
    columns = line.strip().split("  ", maxsplit=1)
    syntax = columns[0].strip()
    description = columns[1].strip() if len(columns) > 1 else ""
    return syntax, description


def clap_sections(text: str) -> tuple[str, list[tuple[str, str]], list[tuple[str, str]]]:
    """Return the ``(summary, arguments, options)`` of clap ``--help`` output."""
    summary = ""
    arguments: list[tuple[str, str]] = []
    options: list[tuple[str, str]] = []
    section = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if line.startswith("Usage:"):
            section = "usage"
        elif stripped == "Arguments:":
            section = "arguments"
        elif stripped == "Options:":
            section = "options"
        elif section == "" and stripped and not summary:
            summary = stripped
        elif section == "arguments" and stripped:
            arguments.append(split_clap_columns(line))
        elif section == "options" and stripped:
            options.append(split_clap_columns(line))
    return summary, arguments, options


def rust_command_names() -> list[str]:
    """Return the top-level ``probe`` subcommands, excluding passthrough helpers."""
    text = run("probe", "--help")
    names: list[str] = []
    collecting = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "Commands:":
            collecting = True
            continue
        if collecting:
            if not stripped or stripped.startswith("Options:"):
                break
            names.append(stripped.split()[0])
    return [name for name in names if name not in {"help", "py"}]


def rust_command(name: str) -> Command:
    """Build a :class:`Command` for the Rust ``probe`` subcommand *name*."""
    summary, arguments, options = clap_sections(run("probe", name, "--help"))
    params = [
        Param(syntax, description)
        for syntax, description in [*arguments, *options]
        if not any(flag in syntax for flag in _BOILERPLATE_FLAGS)
    ]
    return Command(f"probe {name}", summary, params)


def format_default(param: click.Parameter, ctx: click.Context) -> str | None:
    """Return the human-readable default of *param*, if it has one."""
    default = param.get_default(ctx)
    if default is None or default == "":
        return None
    if isinstance(param, click.Option) and param.is_flag:
        primary = param.opts[0].removeprefix("--")
        if default:
            return primary
        if param.secondary_opts:
            return param.secondary_opts[0].removeprefix("--")
    return str(default)


def option_syntax(param: click.Option, ctx: click.Context) -> str:
    """Return the flag syntax of *param*, e.g. ``--probe-log, -f PATH``."""
    if param.secondary_opts:
        return f"{param.opts[0]} / {param.secondary_opts[0]}"
    syntax = ", ".join(param.opts)
    if param.is_flag:
        return syntax
    return f"{syntax} {param.make_metavar(ctx)}"


def option_description(param: click.Option, ctx: click.Context) -> str:
    """Return the description of an option, including its default."""
    parts = [param.help] if param.help else []
    default = format_default(param, ctx)
    if default is not None:
        parts.append(f"[default: {default}]")
    return " ".join(parts)


def argument_description(param: click.Argument, ctx: click.Context) -> str:
    """Return the description of an argument, including its default."""
    default = format_default(param, ctx)
    return f"[default: {default}]" if default is not None else ""


def python_param(param: click.Parameter, ctx: click.Context) -> Param:
    """Convert a click parameter into a :class:`Param`."""
    if isinstance(param, click.Option):
        return Param(option_syntax(param, ctx), option_description(param, ctx))
    if isinstance(param, click.Argument):
        return Param(param.make_metavar(ctx), argument_description(param, ctx))
    msg = f"unexpected parameter type: {type(param)}"
    raise TypeError(msg)


def python_command(name: str, command: click.Command, ctx: click.Context) -> Command:
    """Build a :class:`Command` for the Python subcommand *command*."""
    summary = command.help.splitlines()[0] if command.help else ""
    return Command(name, summary, [python_param(param, ctx) for param in command.params])


def python_commands() -> list[Command]:
    """Return the Python ``probe py`` commands."""
    app = typer.main.get_command(probe_py.cli.app)
    if not isinstance(app, click.Group):
        msg = "probe_py.cli.app is not a command group"
        raise TypeError(msg)
    ctx = click.Context(app, info_name="probe py")
    commands: list[Command] = []
    for name, subcommand in app.commands.items():
        if isinstance(subcommand, click.Group):
            for export_name, export_command in subcommand.commands.items():
                commands.append(
                    python_command(f"probe py {name} {export_name}", export_command, ctx),
                )
        else:
            commands.append(python_command(f"probe py {name}", subcommand, ctx))
    return commands


def escape(text: str) -> str:
    """Escape Markdown table pipes."""
    return text.replace("|", "\\|")


def render(commands: list[Command]) -> str:
    """Render *commands* as the README Markdown."""
    lines = ["# Commands and Options", ""]
    for command in commands:
        lines.append(f"## {command.name}")
        lines.append("")
        if command.summary:
            lines.append(command.summary)
            lines.append("")
        lines.append("| Option | Description |")
        lines.append("|--------|-------------|")
        lines.extend(
            f"| `{escape(param.syntax)}` | {escape(param.description)} |"
            for param in command.params
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    """Regenerate ``cli_doc/README.md``."""
    commands = [rust_command(name) for name in rust_command_names()]
    commands.extend(python_commands())
    README.write_text(render(commands))


if __name__ == "__main__":
    main()
