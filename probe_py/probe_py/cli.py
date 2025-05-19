from typing_extensions import Annotated
import datetime
import dataclasses
import enum
import json
import os
import pathlib
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import typing
import typer
import rich.console
import rich.pretty
import sqlalchemy.orm
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
    dataflow_graph_module.hb_graph_to_dataflow_graph(probe_log, hbg, True)
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
