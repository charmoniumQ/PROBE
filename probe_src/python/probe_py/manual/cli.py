import sys
import typing_extensions
import tarfile
import pathlib
import typer
import rich
from probe_py.generated.parser import parse_probe_log
from probe_py.manual import analysis
from probe_py.manual.workflows import NextflowGenerator, MakefileGenerator
import enum

rich.traceback.install(show_locals=False)

project_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent

A = typing_extensions.Annotated

app = typer.Typer()


@app.command()
def validate(
        input: pathlib.Path = pathlib.Path("probe_log"),
        should_have_files: bool = False,
) -> None:
    if not input.exists():
        typer.secho(f"INPUT {input} does not exist\nUse `PROBE record --output {input} CMD...` to rectify", fg=typer.colors.RED)
        raise typer.Abort()
    console = rich.console.Console(file=sys.stderr)
    prov_log = parse_probe_log(input)
    process_graph = analysis.provlog_to_digraph(prov_log)
    warning_free = True
    for warning in analysis.validate_provlog(prov_log):
        warning_free = False
        console.print(warning, style="red")
    rich.traceback.install(show_locals=False) # Figure out why we need this
    process_graph = analysis.provlog_to_digraph(prov_log)
    for warning in analysis.validate_hb_graph(prov_log, process_graph):
        warning_free = False
        console.print(warning, style="red")
    if should_have_files and not prov_log.has_inodes:
        warning_free = False
        console.print("No files stored in probe log", style="red")
    if not warning_free:
        raise typer.Exit(code=1)


@app.command()
def process_graph(
        input: pathlib.Path = pathlib.Path("probe_log"),
) -> None:
    """
    Write a process graph from PROBE_LOG in DOT/graphviz format.
    """
    if not input.exists():
        typer.secho(f"INPUT {input} does not exist\nUse `PROBE record --output {input} CMD...` to rectify", fg=typer.colors.RED)
        raise typer.Abort()
    prov_log = parse_probe_log(input)
    console = rich.console.Console(file=sys.stderr)
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
        input: pathlib.Path = pathlib.Path("probe_log"),
        output: pathlib.Path = pathlib.Path("dataflow_graph.pkl")
) -> None:
    """
    Write a process graph from PROBE_LOG in DOT/graphviz format.
    """
    if not input.exists():
        typer.secho(f"INPUT {input} does not exist\nUse `PROBE record --output {input} CMD...` to rectify", fg=typer.colors.RED)
        raise typer.Abort()
    probe_log_tar_obj = tarfile.open(input, "r")
    prov_log = parse_probe_log(input)
    probe_log_tar_obj.close()
    console = rich.console.Console(file=sys.stderr)
    process_graph = analysis.provlog_to_digraph(prov_log)
    for warning in analysis.validate_provlog(prov_log):
        console.print(warning, style="red")
    rich.traceback.install(show_locals=False) # Figure out why we need this
    process_graph = analysis.provlog_to_digraph(prov_log)
    for warning in analysis.validate_hb_graph(prov_log, process_graph):
        console.print(warning, style="red")

    dot_string, dataflow_graph = analysis.provlog_to_dataflow_graph(prov_log)
    print(dot_string)

@app.command()
def dump(
        input: pathlib.Path = pathlib.Path("probe_log"),
) -> None:
    """
    Write the data from PROBE_LOG in a human-readable manner.
    """
    if not input.exists():
        typer.secho(f"INPUT {input} does not exist\nUse `PROBE record --output {input} CMD...` to rectify", fg=typer.colors.RED)
        raise typer.Abort()
    processes_prov_log = parse_probe_log(input)
    for pid, process in processes_prov_log.processes.items():
        print(pid)
        for exid, exec_epoch in process.exec_epochs.items():
            print(pid, exid)
            for tid, thread in exec_epoch.threads.items():
                print(pid, exid, tid)
                for op_no, op in enumerate(thread.ops):
                    print(pid, exid, tid, op_no, op.data)
                print()

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
        g = MakefileGenerator()
        script = g.generate_makefile(dataflow_graph)
        output_file = output / "Makefile"
        with output_file.open('a') as outfile:
            outfile.write(script)
        print(script)

    
if __name__ == "__main__":
    app()
