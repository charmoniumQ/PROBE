import typing
import dataclasses
import json
from typing_extensions import Annotated
import pathlib
import subprocess
import shutil
import rich
from probe_py.scp import scp_with_provenance
import os
import typer
import tempfile
import rich.console
import rich.pretty
from .parser import parse_probe_log, parse_probe_log_ctx
from . import analysis
from .workflows import MakefileGenerator, NextflowGenerator
from . import file_closure
from . import graph_utils
from .ssh_argparser import parse_ssh_args
import enum
from .persistent_provenance_db import Process, ProcessInputs, ProcessThatWrites, get_engine
from sqlalchemy.orm import Session
from .analysis import ProcessNode, FileNode
import shlex
import datetime
import random
import socket


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
        only_proc_ops: bool = typer.Option(False, help="For only Exec, Clone, Wait Operations")
) -> None:
    """
    Write a happens-before graph on the operations in probe_log.

    Each operation is an individual exec, open, close, fork, etc.

    If there is a path between two operations A to B, then A happens before B.

    Supports .png, .svg, and .dot
    """
    prov_log = parse_probe_log(probe_log)
    process_graph = analysis.provlog_to_digraph(prov_log, only_proc_ops)
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

def get_host_name() -> int:
    hostname = socket.gethostname()
    rng = random.Random(int(datetime.datetime.now().timestamp()) ^ hash(hostname))
    bits_per_hex_digit = 4
    hex_digits = 8
    random_number = rng.getrandbits(bits_per_hex_digit * hex_digits)
    return random_number

@export_app.command()
def store_dataflow_graph(probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"))->None:
    prov_log = parse_probe_log(probe_log)
    dataflow_graph = analysis.provlog_to_dataflow_graph(prov_log)
    engine = get_engine()
    with Session(engine) as session:
        for node in dataflow_graph.nodes():
            if isinstance(node, ProcessNode):
                print(node)
                new_process = Process(process_id = int(node.pid), parent_process_id = 0, cmd = shlex.join(node.cmd), time = datetime.datetime.now())
                session.add(new_process)

        for (node1, node2) in dataflow_graph.edges():
            if isinstance(node1, ProcessNode) and isinstance(node2, ProcessNode):
                parent_process_id = node1.pid
                child_process = session.get(Process, node2.pid)
                if child_process:
                    child_process.parent_process_id = parent_process_id

            elif isinstance(node1, ProcessNode) and isinstance(node2, FileNode):
                inode_info = node2.inodeOnDevice
                host = get_host_name()
                stat_info = os.stat(node2.file)
                mtime = int(stat_info.st_mtime * 1_000_000_000)
                size = stat_info.st_size
                new_output_inode = ProcessThatWrites(inode = inode_info.inode, process_id = node1.pid, device_major = inode_info.device_major, device_minor  = inode_info.device_minor, host = host, path = node2.file, mtime = mtime, size = size)
                session.add(new_output_inode)

            elif isinstance(node1, FileNode) and isinstance(node2, ProcessNode):
                inode_info = node1.inodeOnDevice
                host = get_host_name()
                stat_info = os.stat(node1.file)
                mtime = int(stat_info.st_mtime * 1_000_000_000)
                size = stat_info.st_size
                new_input_inode = ProcessInputs(inode = inode_info.inode, process_id=node2.pid, device_major=inode_info.device_major, device_minor= inode_info.device_minor, host = host, path = node1.file, mtime=mtime, size=size)
                session.add(new_input_inode)

        root_process = None
        for node in dataflow_graph.nodes():
            if isinstance(node, ProcessNode):
                pid = node.pid
                process_record = session.get(Process, pid)
                if process_record and process_record.parent_process_id == 0:
                    if root_process is not None:
                        print(f"Error: Two parent processes - {pid} and {root_process}")
                        session.rollback()
                        return
                    else:
                        root_process = pid

        session.commit()

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

@export_app.command()
def nextflow(
        output: Annotated[
            pathlib.Path,
            typer.Argument(),
        ] = pathlib.Path("nextflow.nf"),
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Export the probe_log to a Nextflow workflow
    """
    prov_log = parse_probe_log(probe_log)
    dataflow_graph = analysis.provlog_to_dataflow_graph(prov_log)
    g = NextflowGenerator()
    output = pathlib.Path("nextflow.nf")
    script = g.generate_workflow(dataflow_graph)
    output.write_text(script)

@export_app.command()
def process_tree(
    output: Annotated[pathlib.Path, typer.Argument()] = pathlib.Path("provlog-process-tree.png"),
    probe_log: Annotated[
        pathlib.Path,
        typer.Argument(help="output file written by `probe record -o $file`.")
    ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write a process tree from probe_log.

    Digraph shows the clone ops of the parent process and the children.
    """
    prov_log = parse_probe_log(probe_log)
    digraph = analysis.provlog_to_process_tree(prov_log)

    same_rank_groups = []
    for pid, process in prov_log.processes.items():
        group = []
        for epoch_no in sorted(process.exec_epochs.keys()):
            node_id = f"pid{pid}_epoch{epoch_no}"
            if digraph.has_node(node_id):
                group.append(node_id)

        if group:
            same_rank_groups.append(group)

    graph_utils.serialize_graph_proc_tree(digraph, output, same_rank_groups=same_rank_groups)



@export_app.command()
def ops_jsonl(
        probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Export each op to a JSON line.

    The format is subject to change as PROBE evolves. Use with caution!
    """

    def filter_nested_dict(
            dct: typing.Mapping[typing.Any, typing.Any],
    ) -> typing.Mapping[typing.Any, typing.Any]:
        """Converts the bytes in a nested dict to a string"""
        return {
            key: (
                # If dict, Recurse self
                filter_nested_dict(val) if isinstance(val, dict) else
                # If bytes, decode to string
                val.decode(errors="surrogateescape") if isinstance(val, bytes) else
                # Else, do nothing
                val
            )
            for key, val in dct.items()
        }
    stdout_console = rich.console.Console()
    prov_log = parse_probe_log(probe_log)
    for pid, process in prov_log.processes.items():
        for exec_epoch_no, exec_epoch in process.exec_epochs.items():
            for tid, thread in exec_epoch.threads.items():
                for i, op in enumerate(thread.ops):
                    stdout_console.print_json(json.dumps({
                        "pid": pid,
                        "tid": tid,
                        "exec_epoch_no": exec_epoch_no,
                        "i": i,
                        "op": filter_nested_dict(
                            dataclasses.asdict(op),
                        ),
                        "op_data_type": type(op.data).__name__,
                    }))


# Example: scp Desktop/sample_example.txt root@136.183.142.28:/home/remote_dir
@app.command(
context_settings=dict(
        ignore_unknown_options=True,
    ),
)
def scp(cmd: list[str]) -> None:
    scp_with_provenance(cmd)

if __name__ == "__main__":
    app()

