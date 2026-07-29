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
    source_line: bytes
    start: Cursor
    end: Cursor
    message: str


AAAI_ILLEGAL_PACKAGES = [
    # Table 2
    b"authblk",
    b"epsf",
    b"fullpage",
    b"layout",
    b"pgfplots",
    b"times",
    b"babel",
    b"epsfig",
    b"geometry",
    b"lmodern",
    b"psfig",
    b"titlesec",
    b"balance",
    b"euler",
    b"graphics",
    b"navigator",
    b"pstricks",
    b"tocbibind",
    b"cjk",
    b"float",
    b"hyperref",
    b"pdfcomment",
    b"t1enc",
    b"ulem",
    # "Document Preamble"
    b"times",
    b"helvet",
    b"courier"
]
AAAI_ILLEGAL_COMMANDS = [
    # Table 1
    b"abovecaption",
    b"addtolength",
    b"break",
    b"float",
    b"setlength",
    b"trim",
    b"abovedisplay",
    b"baselinestretch",
    b"clearpage",
    b"linespread",
    b"textheight",
    b"addevensidemargin",
    b"belowcaption",
    b"clip",
    b"newpage",
    b"tiny",
    b"addsidemargin",
    b"belowdisplay",
    b"columnsep",
    b"pagebreak",
    b"topmargin",
    # Overlength Papers
    b"columnsep",
    b"float",
    b"topmargin",
    b"topskip",
    # "textheight",
    # "textwidth",
    b"oddsidemargin",
    b"evensizemargin",
    # Tables
    b"resizebox",
]


VERB_RE = re.compile(rb"\\verb")
AAAI_ILLEGAL_PACKAGES_RE = re.compile(rb"\\usepackage\[.*\]{.*(" + b"|".join(AAAI_ILLEGAL_PACKAGES) + rb"\b).*}")
AAAI_ILLEGAL_COMMANDS_RE = re.compile(rb"\\(" + b"|".join(AAAI_ILLEGAL_COMMANDS) + rb")\b")
AAAI_ILLEGAL_VCOMMANDS_RE = re.compile(rb"\\(vspace|vskip){-")
AAAI_ILLEGAL_COMMAND_ARGS_RE = re.compile(rb"\\(textwidth|textheight){")


def check_tex_file(
        file: pathlib.Path,
        aaai_lints: bool,
        missing_refs: collections.abc.Iterable[bytes],
) -> collections.abc.Iterator[Warning]:
    if missing_refs:
        missing_ref_re = re.compile(b"|".join(missing_refs))
    else:
        missing_ref_re = None
    file_position = 0
    for line_number, line in enumerate(file.read_bytes().splitlines()):
        line_number += 1
        for match in VERB_RE.finditer(line):
            yield Warning(
                file,
                line,
                Cursor(line_number, match.start()),
                Cursor(line_number, match.end()),
                "Use \\texttt instead of \\verb, where possible.",
            )
        if missing_ref_re is not None:
            for match in missing_ref_re.finditer(line):
                yield Warning(
                    file,
                    line,
                    Cursor(line_number, match.start()),
                    Cursor(line_number, match.end()),
                    "Missing ref",
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
    for file in dir.glob("**/*.log"):
        missing_refs = check_log_file(file)
    for file in dir.glob("**/*.tex"):
        yield from check_tex_file(file, aaai_lints, missing_refs)


CITATION_UNDEFINED = re.compile(b"Citation `(.*)' on page (.*) undefined")


def check_log_file(log: pathlib.Path) -> collections.abc.Sequence[bytes]:
    ret = []
    for line in log.read_bytes().splitlines():
        if match := CITATION_UNDEFINED.search(line):
            ret.append(match.group(1))
    return tuple(ret)
            
    


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
            print(warning.source_line.decode())
            print(" " * warning.start.column_position + "^" * (warning.end.column_position - warning.start.column_position))
            print()
        if n_warnings == 0:
            print("All good.")
        else:
            print(f"{n_warnings} warnings.")
            raise typer.Exit(1)
    app()
