import collections.abc
import dataclasses
import enum
import pathlib
import typing
from . import util
from . import ptypes
from . import ops
from . import dataflow_graph


It: typing.TypeAlias = collections.abc.Iterable
Map: typing.TypeAlias = collections.abc.Mapping


class WorkflowType(enum.StrEnum):
    SNAKEMAKE = enum.auto()


@dataclasses.dataclass(frozen=True)
class Rule:
    inputs: It[pathlib.Path]
    outputs: It[pathlib.Path]
    cwd: pathlib.Path
    exe: pathlib.Path
    argv: It[bytes]
    env: It[bytes]


def dataflow_graph_to_workflow(
        probe_log: ptypes.ProbeLog,
        dfg: dataflow_graph.DataflowGraph,
        is_important_path: typing.Callable[[pathlib.Path], bool],
        inodes_to_paths: Map[ptypes.Inode, frozenset[pathlib.Path]],
) -> Map[ptypes.ExecPair, Rule]:
    exec_pair_to_quads: Map[ptypes.ExecPair, It[dataflow_graph.Quads]] = util.groupby_dict(
        [
            node
            for node in dfg.nodes()
            if isinstance(node, dataflow_graph.Quads)
        ],
        key_func=lambda quads: next(iter(quads)).exec_pair(),
    )
    # exec_pair_to_ops = {
    #     exec_pair: [probe_log.get_op(quad) for quad in quads]
    #     for exec_pair, quads in exec_pair_to_quads.items()
    # }
    # exec_pair_to_children: Map[ptypes.ExecPair, It[ptypes.ExecPair]] = util.groupby_dict(
    #     [
    #         (parent, ptypes.ExecPair(parent.pid, ptypes.ExecNo(parent.exec_no + 1)))
    #         for parent, nops in exec_pair_to_ops.items()
    #         for op in nops
    #         if isinstance(op.data, ops.ExecOp) and op.data.ferrno == 0
    #     ] + [
    #         (parent, ptypes.ExecPair(ptypes.Pid(op.data.task_id), ptypes.ExecNo(0)))
    #         for parent, nops in exec_pair_to_ops.items()
    #         for op in nops
    #         if isinstance(op.data, ops.CloneOp) and op.data.task_type == ptypes.TaskType.TASK_PID and op.data.ferrno == 0
    #     ],
    #     key_func=lambda pair: pair[0],
    #     value_func=lambda pair: pair[1],
    # )

    rules = {}
    for exec_pair, quadss in exec_pair_to_quads.items():
        inputs = [
            path
            for quads in quadss
            for pred in dfg.predecessors(quads)
            if isinstance(pred, dataflow_graph.IVNs)
            for ivn in pred
            for path in inodes_to_paths.get(ivn.inode, [])
            if is_important_path(path)
        ]
        outputs = [
            path
            for quads in quadss
            for succ in dfg.successors(quads)
            if isinstance(succ, dataflow_graph.IVNs)
            for ivn in succ
            for path in inodes_to_paths.get(ivn.inode, [])
            if is_important_path(path)
        ]
        if inputs or outputs:
            init_quad = ptypes.OpQuad(exec_pair.pid, exec_pair.exec_no, exec_pair.pid.main_thread(), 0)
            init_op_data = probe_log.get_op(init_quad).data
            assert isinstance(init_op_data, ops.InitExecEpochOp)
            rules[exec_pair] = Rule(
                inputs,
                outputs,
                pathlib.Path(init_op_data.cwd.path.decode()),
                pathlib.Path(init_op_data.exe.path.decode()),
                init_op_data.argv,
                init_op_data.env,
            )

    return rules


def to_source(
        workflow_type: WorkflowType,
        directory: pathlib.Path,
        rules: Map[ptypes.ExecPair, Rule],
        include_env: bool,
) -> None:
    {
        WorkflowType.SNAKEMAKE: to_snakemake
    }[workflow_type](directory, rules, include_env)


def to_snakemake(
        directory: pathlib.Path,
        rules: Map[ptypes.ExecPair, Rule],
        include_env: bool
) -> None:
    lines = []
    for exec_pair, rule in rules.items():
        lines.append(b"rule " + str(exec_pair.pid).encode() + b"_" + str(exec_pair.exec_no).encode() + b":")
        lines.append(b"  input:")
        for input in rule.inputs:
            lines.append(b"    \"" + str(input).encode() + b"\"")
        lines.append(b"  output:")
        for output in rule.outputs:
            lines.append(b"    \"" + str(output).encode() + b"\"")
        lines.append(b"  shell:")
        lines.append(b"    env --chdir=\"" + str(rule.cwd).encode() + (b"\" - \"" + b"\" \"".join(rule.env) if include_env else b"") + b"\" \"" + b"\" \"".join(rule.argv) + b"\"")
    (directory / "Snakefile").write_bytes(b"\n".join(lines))
