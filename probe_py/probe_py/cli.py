from typing_extensions import Annotated
import dataclasses
import enum
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import typing
import typer
import rich.console
import rich.pretty
import sqlalchemy.orm
import warnings
from . import dataflow_graph as dataflow_graph_module
from . import file_closure
from . import graph_utils
from . import hb_graph as hb_graph_module
from . import ops
from . import parser
from . import scp as scp_module
from . import ssh_argparser
from . import validators
from .persistent_provenance_db import get_engine


console = rich.console.Console(stderr=True)

project_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent

app = typer.Typer(pretty_exceptions_show_locals=False)
export_app = typer.Typer()
app.add_typer(export_app, name="export")


warnings.simplefilter("once")


@app.command()
def validate(
        path_to_probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
        should_have_files: Annotated[
            bool,
            typer.Option(help="Whether to check that the probe_log was run with copied files.")
        ] = False,
) -> None:
    """Sanity-check probe_log and report errors."""
    sys.excepthook =  sys.__excepthook__
    warning_free = True
    with parser.parse_probe_log_ctx(path_to_probe_log) as probe_log:
        for inode, contents in (probe_log.copied_files or {}).items():
            content_length = contents.stat().st_size
            if inode.size != content_length:
                console.print(f"Blob for {inode} has actual size {content_length}", style="red")
                warning_free = False
        # At this point, the inode storage is gone, but the probe_log is already in memory
    if should_have_files and not probe_log.copied_files:
        warning_free = False
        console.print("No files stored in probe log", style="red")
    for warning in validators.validate_probe_log(probe_log):
        warning_free = False
        console.print(warning, style="red")
    hbg = hb_graph_module.probe_log_to_hb_graph(probe_log)
    dataflow_graph_module.hb_graph_to_dataflow_graph2(probe_log, hbg)
    if not warning_free:
        raise typer.Exit(code=1)


class OpType(enum.StrEnum):
    ALL = enum.auto()
    MINIMAL = enum.auto()
    FILE = enum.auto()


@export_app.command()
def hb_graph(
        output: Annotated[
            pathlib.Path,
            typer.Argument()
        ] = pathlib.Path("ops-graph.png"),
        path_to_probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
        retain_ops: Annotated[
            OpType,
            typer.Option(help="Which ops to include in the graph?")
        ] = OpType.MINIMAL,
) -> None:
    """
    Write a happens-before graph on the operations in probe_log.

    Each operation is an individual exec, open, close, fork, etc.

    If there is a path between two operations A to B, then A happens before B.

    Supports .png, .svg, and .dot
    """
    probe_log = parser.parse_probe_log(path_to_probe_log)
    hbg = hb_graph_module.probe_log_to_hb_graph(probe_log)
    match retain_ops:
        case OpType.ALL:
            pass
        case OpType.MINIMAL:
            hbg = hb_graph_module.retain_only(probe_log, hbg, lambda _node, _op: False)
        case OpType.FILE:
            hbg = hb_graph_module.retain_only(probe_log, hbg, lambda node, op: isinstance(op.data, (ops.OpenOp, ops.CloseOp, ops.DupOp, ops.ExecOp)))
    hb_graph_module.label_nodes(probe_log, hbg, retain_ops == OpType.ALL)
    graph_utils.serialize_graph(hbg, output)

    
@export_app.command()
def dataflow_graph(
        output: Annotated[
            pathlib.Path,
            typer.Argument()
        ] = pathlib.Path("dataflow-graph.png"),
        path_to_probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write a dataflow graph for probe_log.

    Dataflow shows the name of each proceess, its read files, and its write files.
    """
    probe_log = parser.parse_probe_log(path_to_probe_log)
    hbg = hb_graph_module.probe_log_to_hb_graph(probe_log)
    hb_graph_module.label_nodes(probe_log, hbg)
    dfg = dataflow_graph_module.hb_graph_to_dataflow_graph2(probe_log, hbg)
    print("done with dfg; starting compression")
    compressed_dfg = dataflow_graph_module.combine_indistinguishable_inodes(dfg)
    print("done with compression; starting label")
    dataflow_graph_module.label_nodes(probe_log, compressed_dfg)
    print("done with label; starting serialize")
    data = compressed_dfg.nodes(data=True)
    graph_utils.serialize_graph(compressed_dfg, output, lambda node: data[node]["id"])
    print("done with serialize")


@export_app.command()
def store_dataflow_graph(path_to_probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"))->None:
    # probe_log = parser.parse_probe_log(path_to_probe_log)
    # hbg = hb_graph_module.probe_log_to_hb_graph(probe_log)
    # dfg = dataflow_graph_module.hb_graph_to_dataflow_graph(probe_log, hbg, True)
    engine = get_engine()
    with sqlalchemy.orm.Session(engine) as session:
        raise NotImplementedError()
        # for node in dfg.nodes():
            # if isinstance(node, ProcessNode):
            #     new_process = Process(process_id = int(node.pid), parent_process_id = 0, cmd = shlex.join(node.cmd), time = datetime.datetime.now())
            #     session.add(new_process)

        # for (node1, node2) in dfg.edges():
            # if isinstance(node1, ProcessNode) and isinstance(node2, ProcessNode):
            #     parent_process_id = node1.pid
            #     child_process = session.get(Process, node2.pid)
            #     if child_process:
            #         child_process.parent_process_id = parent_process_id

            # elif isinstance(node1, ProcessNode) and isinstance(node2, FileAccess):
            #     inode_info = node2.inode_version
            #     host = get_host_name()
            #     stat_info = os.stat(node2.path)
            #     mtime = int(stat_info.st_mtime * 1_000_000_000)
            #     size = stat_info.st_size
            #     new_output_inode = ProcessThatWrites(
            #         inode=inode_info.inode,
            #         process_id=node1.pid,
            #         device=inode_info.inode.device,
            #         host=host,
            #         path=node2.path,
            #         mtime=mtime,
            #         size=size,
            #     )
            #     session.add(new_output_inode)

            # elif isinstance(node1, FileAccess) and isinstance(node2, ProcessNode):
            #     inode_info = node1.inode_version
            #     host = get_host_name()
            #     stat_info = os.stat(node1.path)
            #     mtime = int(stat_info.st_mtime * 1_000_000_000)
            #     size = stat_info.st_size
            #     new_input_inode = ProcessInputs(
            #         inode=inode_info.inode,
            #         process_id=node2.pid,
            #         device=inode_info.inode.device,
            #         host=host,
            #         path=node1.path,
            #         mtime=mtime,
            #         size=size,
            #     )
            #     session.add(new_input_inode)

        raise NotImplementedError()
        # root_process = None
        # for node in dataflow_graph_module.nodes():
        #     if isinstance(node, ProcessNode):
        #         pid = node.pid
        #         process_record = session.get(Process, pid)
        #         if process_record and process_record.parent_process_id == 0:
        #             if root_process is not None:
        #                 print(f"Error: Two parent processes - {pid} and {root_process}")
        #                 session.rollback()
        #                 return
        #             else:
        #                 root_process = pid

        session.commit()


@export_app.command()
def debug_text(
        path_to_probe_log: Annotated[
            pathlib.Path,
            typer.Argument(help="output file written by `probe record -o $file`."),
        ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write the data from probe_log in a human-readable manner.
    """
    out_console = rich.console.Console()
    with parser.parse_probe_log_ctx(path_to_probe_log) as probe_log:
        for pid, process in sorted(probe_log.processes.items()):
            out_console.rule(f"{pid}")
            for exid, exec_epoch in sorted(process.execs.items()):
                out_console.rule(f"{pid} {exid}")
                for tid, thread in sorted(exec_epoch.threads.items()):
                    out_console.rule(f"{pid} {exid} {tid}")
                    for op_no, op in enumerate(thread.ops):
                        out_console.print(op_no)
                        rich.pretty.pprint(
                            op.data,
                            console=out_console,
                            max_string=None,
                        )
        for ino_ver, path in sorted(probe_log.copied_files.items()):
            out_console.print(
                f"device={ino_ver.inode.device.major_id}.{ino_ver.inode.device.minor_id} inode={ino_ver.inode.number} mtime={ino_ver.mtime} -> {ino_ver.size} blob"
            )


@export_app.command()
def docker_image(
        image_name: str,
        path_to_probe_log: Annotated[
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
    with parser.parse_probe_log_ctx(path_to_probe_log) as probe_log:
        if not probe_log.probe_options.copy_files:
            console.print("No files stored in probe log", style="red")
            raise typer.Exit(code=1)
        file_closure.build_oci_image(
            probe_log,
            image_name,
            True,
            verbose,
            console,
        )

@export_app.command()
def oci_image(
        image_name: str,
        path_to_probe_log: Annotated[
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
    with parser.parse_probe_log_ctx(path_to_probe_log) as probe_log:
        if not probe_log.probe_options.copy_files:
            console.print("No files stored in probe log", style="red")
            raise typer.Exit(code=1)
        file_closure.build_oci_image(
            probe_log,
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

    flags, destination, remote_host = ssh_argparser.parse_ssh_args(ssh_args)

    ssh_cmd = ["ssh"] + flags

    libprobe = pathlib.Path(os.environ["PROBE_LIB"]) / ("libprobe-dbg.so" if debug else "libprobe.so")
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

    # Prepare the remote command with LD_PRELOAD and PROBE_DIR
    ld_preload = f"{remote_temp_dir}/{libprobe.name}"

    env = ["env", f"LD_PRELOAD={ld_preload}", f"PROBE_DIR={remote_probe_dir}"]
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


@export_app.command()
def process_tree(
    output: Annotated[pathlib.Path, typer.Argument()] = pathlib.Path("probe_log-process-tree.png"),
    path_to_probe_log: Annotated[
        pathlib.Path,
        typer.Argument(help="output file written by `probe record -o $file`.")
    ] = pathlib.Path("probe_log"),
) -> None:
    """
    Write a process tree from probe_log.

    Digraph shows the clone ops of the parent process and the children.
    """
    raise NotImplementedError()
    # probe_log = parser.parse_probe_log(path_to_probe_log)
    # hbg = hb_graph_module.probe_log_to_hb_graph(probe_log)
    # pt = process_tree_module.hb_graph_to_process_tree(probe_log, hbg)
    # graph_utils.serialize_graph_proc_tree(
    #     pt,
    #     output,
    #     # same_rank_groups=same_rank_groups,
    # )


@export_app.command()
def ops_jsonl(
        path_to_probe_log: Annotated[
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
    probe_log = parser.parse_probe_log(path_to_probe_log)
    for pid, process in probe_log.processes.items():
        for exec_epoch_no, exec_epoch in process.execs.items():
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
    scp_module.scp_with_provenance(cmd)

if __name__ == "__main__":
    app()
