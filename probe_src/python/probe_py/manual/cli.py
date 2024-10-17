from typing_extensions import Annotated
import pathlib
import typer
import rich.console
import rich.pretty
from ..generated.parser import parse_probe_log, parse_probe_log_ctx
from . import analysis
from .workflows import NextflowGenerator, MakefileGenerator
from . import file_closure
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


@app.command()
def process_graph(
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write a process graph from PROBE_LOG in DOT/graphviz format.
    """
    prov_log = parse_probe_log(probe_log)
    process_graph = analysis.provlog_to_digraph(prov_log)
    for warning in analysis.validate_provlog(prov_log):
        console.print(warning, style="red")
    rich.traceback.install(show_locals=False) # Figure out why we need this
    process_graph = analysis.provlog_to_digraph(prov_log)
    for warning in analysis.validate_hb_graph(prov_log, process_graph):
        console.print(warning, style="red")
    print(analysis.digraph_to_pydot_string(prov_log, process_graph))
    
@app.command()
def dataflow_graph(
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
        output: pathlib.Path = pathlib.Path("dataflow_graph.pkl")
) -> None:
    """
    Write a process graph from PROBE_LOG in DOT/graphviz format.
    """
    prov_log = parse_probe_log(probe_log)
    process_graph = analysis.provlog_to_digraph(prov_log)
    for warning in analysis.validate_provlog(prov_log):
        console.print(warning, style="red")
    rich.traceback.install(show_locals=False) # Figure out why we need this
    process_graph = analysis.provlog_to_digraph(prov_log)
    for warning in analysis.validate_hb_graph(prov_log, process_graph):
        console.print(warning, style="red")

    dot_string, dataflow_graph = analysis.provlog_to_dataflow_graph(prov_log)
    print(dot_string)

@export_app.command()
def text(
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write the data from PROBE_LOG in a human-readable manner.
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
            out_console.print(f"device={ivl.device_major}.{ivl.device_minor} inode={ivl.inode} mtime={ivl.tv_sec}.{ivl.tv_nsec} -> {tvl.size} blob")

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

    For example,

        probe record python -c 'import numpy; print(numpy.array([1,2,3]).mean())'
        probe docker-image python-numpy:latest
        docker run --rm python-numpy:latest

    """
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

@app.command()
def export(
    input: pathlib.Path = pathlib.Path("probe_log"),
    output_format: OutputFormat = typer.Option(OutputFormat.nextflow, help="Select output format", show_default=True),
    output: pathlib.Path = pathlib.Path("workflow"),
) -> None:
    """
    Export the dataflow graph to Workflow (Nextflow and Makefile).
    """
    output.mkdir(parents=True, exist_ok=True)
    if not input.exists():
        typer.secho(f"INPUT {input} does not exist", fg=typer.colors.RED)
        raise typer.Abort()

    prov_log = parse_probe_log(input)
    _, dataflow_graph = analysis.provlog_to_dataflow_graph(prov_log)

    if output_format == OutputFormat.nextflow : 
        generator = NextflowGenerator()
        script = generator.generate_workflow(dataflow_graph)
        output_file = output / "nextflow.nf"
        print(script)
        with output_file.open('a') as outfile:
            outfile.write(script)
    elif output_format == OutputFormat.makefile : 
        g = MakefileGenerator(output_dir="experiments")

        # Generate Makefile content
        makefile_content = g.generate_makefile(dataflow_graph)

        # Write to Makefile
        with open("Makefile", "w") as f:
            f.write(makefile_content)

        print(makefile_content)

    
if __name__ == "__main__":
    app()
