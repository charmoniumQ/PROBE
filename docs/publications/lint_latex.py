from __future__ import annotations
import collections.abc
import dataclasses
import pathlib
import re
import typing


@dataclasses.dataclass
class Cursor:
    line_number: int
    column_position: int


@dataclasses.dataclass
class Warning:
    file: pathlib.Path
    source_line: str
    start: Cursor
    end: Cursor
    message: str


AAAI_ILLEGAL_PACKAGES = [
    # Table 2
    "authblk",
    "epsf",
    "fullpage",
    "layout",
    "pgfplots",
    "times",
    "babel",
    "epsfig",
    "geometry",
    "lmodern",
    "psfig",
    "titlesec",
    "balance",
    "euler",
    "graphics",
    "navigator",
    "pstricks",
    "tocbibind",
    "cjk",
    "float",
    "hyperref",
    "pdfcomment",
    "t1enc",
    "ulem",
    # "Document Preamble"
    "times",
    "helvet",
    "courier"
]
AAAI_ILLEGAL_COMMANDS = [
    # Table 1
    "abovecaption",
    "addtolength",
    "break",
    "float",
    "setlength",
    "trim",
    "abovedisplay",
    "baselinestretch",
    "clearpage",
    "linespread",
    "textheight",
    "addevensidemargin",
    "belowcaption",
    "clip",
    "newpage",
    "tiny",
    "addsidemargin",
    "belowdisplay",
    "columnsep",
    "pagebreak",
    "topmargin",
    # Overlength Papers
    "columnsep",
    "float",
    "topmargin",
    "topskip",
    # "textheight",
    # "textwidth",
    "oddsidemargin",
    "evensizemargin",
    # Tables
    "resizebox",
]


VERB_RE = re.compile(r"\\verb")
AAAI_ILLEGAL_PACKAGES_RE = re.compile(r"\\usepackage\[.*\]{.*(" + "|".join(AAAI_ILLEGAL_PACKAGES) + r").*}")
AAAI_ILLEGAL_COMMANDS_RE = re.compile(r"\\(" + "|".join(AAAI_ILLEGAL_COMMANDS) + ")")
AAAI_ILLEGAL_VCOMMANDS_RE = re.compile(r"\\(vspace|vskip){-")
AAAI_ILLEGAL_COMMAND_ARGS_RE = re.compile(r"\\(textwidth|textheight){")


def check_tex_file(
        file: pathlib.Path,
        aaai_lints: bool,
) -> collections.abc.Iterator[Warning]:
    file_position = 0
    for line_number, line in enumerate(file.read_text().split("\n")):
        line_number += 1
        for match in VERB_RE.finditer(line):
            yield Warning(
                file,
                line,
                Cursor(line_number, match.start()),
                Cursor(line_number, match.end()),
                "Use \\texttt instead of \\verb, where possible.",
            )
        if aaai_lints:
            for match in AAAI_ILLEGAL_PACKAGES_RE.finditer(line):
                yield Warning(
                    file,
                    line,
                    Cursor(line_number, match.start(1)),
                    Cursor(line_number, match.end(1)),
                    "AAAI does not allow this package",
                )
            for match in AAAI_ILLEGAL_COMMANDS_RE.finditer(line):
                yield Warning(
                    file,
                    line,
                    Cursor(line_number, match.start()),
                    Cursor(line_number, match.end()),
                    "AAAI does not allow this command",
                )
            for match in AAAI_ILLEGAL_VCOMMANDS_RE.finditer(line):
                yield Warning(
                    file,
                    line,
                    Cursor(line_number, match.start()),
                    Cursor(line_number, match.end()),
                    "AAAI does not allow this command",
                )
            for match in AAAI_ILLEGAL_COMMAND_ARGS_RE.finditer(line):
                yield Warning(
                    file,
                    line,
                    Cursor(line_number, match.start()),
                    Cursor(line_number, match.end()),
                    "AAAI does not allow this command with an argument",
                )
        file_position += len(line) + 1


def check_directory(
        dir: pathlib.Path,
        aaai_lints: bool,
) -> collections.abc.Iterator[Warning]:
    for file in dir.glob("**/*.tex"):
        yield from check_tex_file(file, aaai_lints)


if __name__ == "__main__":
    import typer
    app = typer.Typer()
    @app.command()
    def main(
            directory: pathlib.Path,
            aaai_lints: typing.Annotated[bool, typer.Option()] = False,
    ) -> None:
        n_warnings = 0
        for warning in check_directory(directory, aaai_lints):
            n_warnings += 1
            print(f"{warning.file}:{warning.start.line_number}:{warning.start.column_position}: {warning.message}")
            print(warning.source_line)
            print(" " * warning.start.column_position + "^" * (warning.end.column_position - warning.start.column_position))
            print()
        if n_warnings == 0:
            print("All good.")
        else:
            print(f"{n_warnings} warnings.")
            raise typer.Exit(1)
    app()
