import shutil
import subprocess
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

    rich.traceback.install(show_locals=False)
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
    with tarfile.open(input, "r") as tar_obj:
        for inode, file_name in prov_log.inodes.items():
            try:
                content = tar_obj.extractfile(file_name)
            except KeyError:
                console.print(f"probe_log cannot extract {inode}")
                warning_free = False
                continue
            if content is None:
                console.print(f"probe_log cannot extract {inode}")
                warning_free = False
                continue
            content_length = len(content.read())
            if inode.size != content_length:
                console.print(f"Blob for {inode} has actual size {content_length}", style="red")
                warning_free = False
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

@app.command()
def oci(
    directory: pathlib.Path = typer.Argument(..., exists=True, file_okay=False, help="The directory containing files to build the OCI image."),
    image_name: str = typer.Argument(..., help="The name of the OCI image."),
    tag: str = typer.Argument(..., help="The tag of the OCI image."),
    tar_output: bool = typer.Option(False, help="Whether to output a tar file of the image."),
    docker_tar: bool = typer.Option(False, help="Whether to create a Docker-compatible tar file."),
    load_docker: bool = typer.Option(False, help="Whether to load the image into Docker."),
    load_podman: bool = typer.Option(False, help="Whether to load the image into Podman."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
) -> None:
    """
    Build an OCI image from a specified directory with options for tar output and loading into Docker/Podman.
    """
    if not directory.is_dir():
        raise ValueError(f"The directory {directory} does not exist or is not a directory.")

    image_tag = f"{image_name}:{tag}"
    oci_tar_file = pathlib.Path(f"{image_name}.tar")
    docker_tar_file = pathlib.Path(f"{image_name}-docker.tar")

    try:
        if verbose:
            typer.secho(f"Creating OCI image '{image_tag}' from directory '{directory}'...", fg=typer.colors.GREEN)

        container_id = subprocess.check_output(["buildah", "from", "scratch"]).strip().decode('utf-8')
        if verbose:
            typer.secho(f"Created container with ID: {container_id}", fg=typer.colors.GREEN)

        subprocess.run(f"buildah add {container_id} {str(directory)} /",stdout=subprocess.DEVNULL if not verbose else None, stderr=subprocess.DEVNULL if not verbose else None, shell=True, check=True)
        if verbose:
            typer.secho(f"Added contents of {directory} to container {container_id}.", fg=typer.colors.GREEN)

        subprocess.run(f"buildah commit {container_id} {image_tag}",stdout=subprocess.DEVNULL if not verbose else None, stderr=subprocess.DEVNULL if not verbose else None, shell=True, check=True)
        if verbose:
            typer.secho(f"OCI image '{image_tag}' built successfully.", fg=typer.colors.GREEN)

        subprocess.run(f"buildah push {image_tag} oci-archive:{oci_tar_file}",stdout=subprocess.DEVNULL if not verbose else None, stderr=subprocess.DEVNULL if not verbose else None, shell=True, check=True)
        if verbose:
            typer.secho(f"OCI image saved as '{oci_tar_file}'.", fg=typer.colors.GREEN)

        subprocess.run(f"buildah push {image_tag} docker-archive:{docker_tar_file}",stdout=subprocess.DEVNULL if not verbose else None, stderr=subprocess.DEVNULL if not verbose else None, shell=True, check=True)
        if verbose:
            typer.secho(f"OCI image saved as Docker-compatible tar '{docker_tar_file}'.", fg=typer.colors.GREEN)

        if load_docker:
            subprocess.run(f"docker load -i {docker_tar_file}",stdout=subprocess.DEVNULL if not verbose else None, stderr=subprocess.DEVNULL if not verbose else None, shell=True, check=True)
            if verbose:
                typer.secho(f"OCI image '{image_tag}' loaded into Docker.", fg=typer.colors.GREEN)

        if not load_podman:
            subprocess.run(f"podman rmi {image_tag}",stdout=subprocess.DEVNULL if not verbose else None, stderr=subprocess.DEVNULL if not verbose else None, shell=True)
        else:
            if verbose:
                typer.secho(f"OCI image '{image_tag}' loaded into Podman.", fg=typer.colors.GREEN)

    except subprocess.CalledProcessError as e:
        typer.secho(f"Error occurred: {e}", fg=typer.colors.RED)
        raise

    finally:
        tar_dir = pathlib.Path("tar")
        tar_dir.mkdir(exist_ok=True)

        if tar_output and oci_tar_file.exists():
            shutil.move(str(oci_tar_file), tar_dir / oci_tar_file.name)
            if verbose:
                typer.secho(f"OCI tar file saved in {tar_dir / oci_tar_file.name}", fg=typer.colors.GREEN)
        elif oci_tar_file.exists():
            oci_tar_file.unlink()

        if docker_tar and docker_tar_file.exists():
            shutil.move(str(docker_tar_file), tar_dir / docker_tar_file.name)
            if verbose:
                typer.secho(f"Docker tar file saved in {tar_dir / docker_tar_file.name}", fg=typer.colors.GREEN)
        elif docker_tar_file.exists():
            docker_tar_file.unlink()

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
