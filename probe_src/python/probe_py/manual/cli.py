import sys
import typing_extensions
import tarfile
import pathlib
import typer
import rich
from probe_py.manual.ssh_argparser import parse_ssh_args
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

@app.command(
    context_settings=dict(
        ignore_unknown_options=True,
    ),
)
def ssh(
        ssh_args: list[str],
        debug: bool = typer.Option(default=False, help="Run verbose & debug build of libprobe"),
) -> None:
    """
    Wrap SSH and record provenance of the remote command.
    """

    flags, destination, remote_host = parse_ssh_args(ssh_args)
        
    ssh_cmd = ["ssh"] + flags 

    libprobe = pathlib.Path(os.environ["__PROBE_LIB"]) / ("libprobe-dbg.so" if debug else "libprobe.so")
    if not libprobe.exists():
        typer.secho(f"Libprobe not found at {libprobe}", fg=typer.colors.RED)
        raise typer.Abort()

    # Create a temporary directory on the local machine
    local_temp_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"probe_log_{os.getpid()}"))

    # Check if remote platform matches local platform
    remote_gcc_machine_cmd = ssh_cmd + ["gcc", "-dumpmachine"]
    local_gcc_machine_cmd = ["gcc", "-dumpmachine"]

    remote_gcc_machine = subprocess.check_output(remote_gcc_machine_cmd)
    local_gcc_machine = subprocess.check_output(local_gcc_machine_cmd)

    if remote_gcc_machine != local_gcc_machine:
        raise NotImplementedError("Remote platform is different from local platform")

    # Upload libprobe.so to the remote temporary directory
    remote_temp_dir_cmd = ssh_cmd + [destination] + ["mktemp", "-d", "/tmp/probe_log_XXXXXX"]
    remote_temp_dir = subprocess.check_output(remote_temp_dir_cmd).decode().strip()
    remote_probe_dir = f"{remote_temp_dir}/probe_dir"

    ssh_g = subprocess.run(ssh_cmd + [destination] + ['-G'],stdout=subprocess.PIPE)
    ssh_g_op = ssh_g.stdout.decode().strip().splitlines()

    ssh_pair = []
    for pair in ssh_g_op:
        ssh_pair.append(pair.split())

    scp_cmd = ["scp"]
    for option in ssh_g_op:
        key_value = option.split(' ', 1)
        if len(key_value) == 2:
            key, value = key_value
            scp_cmd.append(f"-o {key}={value}")

    scp_args =[str(libprobe),f"{destination}:{remote_temp_dir}"]
    scp_cmd.extend(scp_args)

    subprocess.run(scp_cmd,check=True)

    # Prepare the remote command with LD_PRELOAD and __PROBE_DIR
    ld_preload = f"{remote_temp_dir}/{libprobe.name}"

    env = ["env", f"LD_PRELOAD={ld_preload}", f"__PROBE_DIR={remote_probe_dir}"]
    proc = subprocess.run(ssh_cmd + [destination] + env + remote_host)

    # Download the provenance log from the remote machine

    remote_tar_file = f"{remote_temp_dir}.tar.gz"
    tar_cmd = ssh_cmd + [destination] + ["tar", "-czf", remote_tar_file, "-C", remote_temp_dir, "."]
    subprocess.run(tar_cmd, check=True)

    # Download the tarball to the local machine
    local_tar_file = local_temp_dir / f"{remote_temp_dir.split('/')[-1]}.tar.gz"
    scp_download_cmd = ["scp"] + scp_cmd[1:-2] + [f"{destination}:{remote_tar_file}", str(local_tar_file)]
    typer.secho(f"PROBE log downloaded at: {scp_download_cmd[-1]}",fg=typer.colors.GREEN)
    subprocess.run(scp_download_cmd, check=True)

    # Clean up the remote temporary directory
    remote_cleanup_cmd = ssh_cmd + [destination] + [f"rm -rf {remote_temp_dir}"]
    subprocess.run(remote_cleanup_cmd, check=True)

    # Clean up the local temporary directory
    shutil.rmtree(local_temp_dir)

    raise typer.Exit(proc.returncode)

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

