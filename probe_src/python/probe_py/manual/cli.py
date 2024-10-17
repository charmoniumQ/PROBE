from typing_extensions import Annotated
import pathlib
import typer
import rich.console
import rich.pretty
from ..generated.parser import parse_probe_log, parse_probe_log_ctx
from . import analysis
from .workflows import MakefileGenerator
from . import file_closure
from . import graph_utils
import enum


console = rich.console.Console(stderr=True)

project_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent

app = typer.Typer(pretty_exceptions_show_locals=False)
export_app = typer.Typer()
app.add_typer(export_app, name="export")



@app.command()
def validate(
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
        should_have_files: Annotated[
            bool,
            typer.Argument(help="Whether to check that the probe_log was run with --copy-files.")
        ] = False,
) -> None:
    """Sanity-check probe_log and report errors."""
    warning_free = True
    with parse_probe_log_ctx(probe_log) as parsed_probe_log:
        for inode, contents in parsed_probe_log.inodes.items():
            content_length = contents.stat().st_size
            if inode.size != content_length:
                console.print(f"Blob for {inode} has actual size {content_length}", style="red")
                warning_free = False
        # At this point, the inode storage is gone, but the probe_log is already in memory
    if should_have_files and not parsed_probe_log.has_inodes:
        warning_free = False
        console.print("No files stored in probe log", style="red")
    process_graph = analysis.provlog_to_digraph(parsed_probe_log)
    for warning in analysis.validate_provlog(parsed_probe_log):
        warning_free = False
        console.print(warning, style="red")
    process_graph = analysis.provlog_to_digraph(parsed_probe_log)
    for warning in analysis.validate_hb_graph(parsed_probe_log, process_graph):
        warning_free = False
        console.print(warning, style="red")
    if not warning_free:
        raise typer.Exit(code=1)


@export_app.command()
def ops_graph(
        output: Annotated[
            pathlib.Path,
            typer.Argument()
        ] = pathlib.Path("ops-graph.png"),
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write a happens-before graph on the operations in probe_log.

    Each operation is an individual exec, open, close, fork, etc.

    If there is a path between two operations A to B, then A happens before B.

    Supports .png, .svg, and .dot
    """
    prov_log = parse_probe_log(probe_log)
    process_graph = analysis.provlog_to_digraph(prov_log)
    analysis.color_hb_graph(prov_log, process_graph)
    graph_utils.serialize_graph(process_graph, output)

    
@export_app.command()
def dataflow_graph(
        output: Annotated[
            pathlib.Path,
            typer.Argument()
        ] = pathlib.Path("dataflow-graph.png"),
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write a dataflow graph for probe_log.

    Dataflow shows the name of each proceess, its read files, and its write files.
    """
    prov_log = parse_probe_log(probe_log)
    dataflow_graph = analysis.provlog_to_dataflow_graph(prov_log)
    graph_utils.serialize_graph(dataflow_graph, output)


@export_app.command()
def debug_text(
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write the data from probe_log in a human-readable manner.
    """
    out_console = rich.console.Console()
    with parse_probe_log_ctx(probe_log) as prov_log:
        for pid, process in sorted(prov_log.processes.items()):
            out_console.rule(f"{pid}")
            for exid, exec_epoch in sorted(process.exec_epochs.items()):
                out_console.rule(f"{pid} {exid}")
                for tid, thread in sorted(exec_epoch.threads.items()):
                    out_console.rule(f"{pid} {exid} {tid}")
                    for op_no, op in enumerate(thread.ops):
                        out_console.print(op_no)
                        rich.pretty.pprint(
                            op.data,
                            console=console,
                            max_string=40,
                        )
        for ivl, path in sorted(prov_log.inodes.items()):
            out_console.print(f"device={ivl.device_major}.{ivl.device_minor} inode={ivl.inode} mtime={ivl.tv_sec}.{ivl.tv_nsec} -> {ivl.size} blob")

@export_app.command()
def docker_image(
        image_name: str,
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
        verbose: bool = True,
) -> None:
    """Generate a docker image from a probe_log with --copy-files

    This may not work with moderately complex applications, like Python, yet.

    File an issue if this is something you are interested in, and we will prioritize it.

    For example,

        probe record python -c 'import numpy; print(numpy.array([1,2,3]).mean())'
        probe docker-image python-numpy:latest
        docker run --rm python-numpy:latest

    """
    if image_name.count(":") == 0:
        image_name = f"{image_name}:latest"
    if image_name.count(":") != 1:
        console.print(f"Invalid image name {image_name}", style="red")
        raise typer.Exit(code=1)
    with parse_probe_log_ctx(probe_log) as prov_log:
        if not prov_log.has_inodes:
            console.print("No files stored in probe log", style="red")
            raise typer.Exit(code=1)
        file_closure.build_oci_image(
            prov_log,
            image_name,
            True,
            verbose,
            console,
        )

@export_app.command()
def oci_image(
        image_name: str,
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
        verbose: bool = True,
) -> None:
    """Generate an OCI image from a probe_log with --copy-files

    This may not work with moderately complex applications, like Python, yet.

    File an issue if this is something you are interested in, and we will prioritize it.

    For example,

        probe record python -c 'import numpy; print(numpy.array([1,2,3]).mean())'
        probe oci-image python-numpy:latest
        podman run --rm python-numpy:latest

    """
    with parse_probe_log_ctx(probe_log) as prov_log:
        if not prov_log.has_inodes:
            console.print("No files stored in probe log", style="red")
            raise typer.Exit(code=1)
        file_closure.build_oci_image(
            prov_log,
            image_name,
            False,
            verbose,
            console,
        )


class OutputFormat(str, enum.Enum):
    makefile = "makefile"
    nextflow = "nextflow"

@export_app.command()
def makefile(
        output: Annotated[
            pathlib.Path,
            typer.Argument(),
        ] = pathlib.Path("Makefile"),
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Export the probe_log to a Makefile
    """
    prov_log = parse_probe_log(probe_log)
    dataflow_graph = analysis.provlog_to_dataflow_graph(prov_log)
    g = MakefileGenerator()
    output = pathlib.Path("Makefile")
    script = g.generate_makefile(dataflow_graph)
    output.write_text(script)


if __name__ == "__main__":
    app()
