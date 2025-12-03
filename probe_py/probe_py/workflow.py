from __future__ import annotations
import collections.abc
import dataclasses
import enum
import itertools
import pathlib
import shlex
import typing
import networkx
from . import dataflow_graph
from . import graph_utils
from . import ops
from . import ptypes
from . import util


It: typing.TypeAlias = collections.abc.Iterable
Seq: typing.TypeAlias = collections.abc.Sequence
Map: typing.TypeAlias = collections.abc.Mapping


class WorkflowType(enum.StrEnum):
    SNAKEMAKE = enum.auto()


@dataclasses.dataclass(frozen=True)
class Rule:
    inputs: It[pathlib.Path]
    outputs: It[pathlib.Path]
    cwd: pathlib.Path
    exe: pathlib.Path
    argv: Seq[bytes]
    env: It[bytes]

    def deduplicate(self) -> Rule:
        return Rule(
            tuple(frozenset(self.inputs)),
            tuple(frozenset(self.outputs)),
            self.cwd,
            self.exe,
            self.argv,
            self.env
        )

    def filter(self: Rule, predicate: typing.Callable[[pathlib.Path], bool]) -> Rule:
        return Rule(
            tuple(filter(predicate, self.inputs)),
            tuple(filter(predicate, self.outputs)),
            self.cwd,
            self.exe,
            self.argv,
            self.env
        )

    @staticmethod
    def combine(main: Rule, children: It[Rule]) -> Rule:
        return Rule(
            tuple([*main.inputs, *itertools.chain.from_iterable(child.inputs for child in children)]),
            tuple([*main.outputs, *itertools.chain.from_iterable(child.outputs for child in children)]),
            main.cwd,
            main.exe,
            main.argv,
            main.env,
        )


def dataflow_graph_to_workflow(
        probe_log: ptypes.ProbeLog,
        dfg: dataflow_graph.DataflowGraph,
        is_important_path: typing.Callable[[pathlib.Path], bool],
        is_important_cmd: typing.Callable[[Seq[bytes]], bool],
        inodes_to_paths: Map[ptypes.Inode, It[pathlib.Path]],
) -> It[Rule]:
    exec_pair_to_quads: Map[ptypes.ExecPair, It[dataflow_graph.Quads]] = util.groupby_dict(
        [
            node
            for node in dfg.nodes()
            if isinstance(node, dataflow_graph.Quads)
        ],
        key_func=lambda quads: next(iter(quads)).exec_pair(),
    )

    all_rules = {}
    for exec_pair, quadss in exec_pair_to_quads.items():
        inputs = frozenset(
            path
            for quads in quadss
            for pred in dfg.predecessors(quads)
            if isinstance(pred, dataflow_graph.IVNs)
            for ivn in pred
            for path in inodes_to_paths.get(ivn.inode, [])
        )
        outputs = frozenset(
            path
            for quads in quadss
            for succ in dfg.successors(quads)
            if isinstance(succ, dataflow_graph.IVNs)
            for ivn in succ
            for path in inodes_to_paths.get(ivn.inode, [])
        )
        init_quad = ptypes.OpQuad(exec_pair.pid, exec_pair.exec_no, exec_pair.pid.main_thread(), 0)
        init_op_data = probe_log.get_op(init_quad).data
        assert isinstance(init_op_data, ops.InitExecEpochOp)
        all_rules[exec_pair] = Rule(
            tuple(inputs),
            tuple(outputs),
            pathlib.Path(init_op_data.cwd.path.decode()),
            pathlib.Path(init_op_data.exe.path.decode()),
            tuple(init_op_data.argv),
            tuple(init_op_data.env),
        )
    del exec_pair

    exec_pair_graph = get_exec_pair_graph(probe_log)
    root_exec_pair = ptypes.ExecPair(probe_log.get_root_pid(), ptypes.ExecNo(0))
    traversal = graph_utils.search_with_pruning(exec_pair_graph, root_exec_pair, breadth_first=True)
    rules: list[Rule] = []
    for curr_exec_pair in traversal:
        assert curr_exec_pair is not None
        if curr_exec_pair in all_rules:
            main_rule = all_rules[curr_exec_pair]
            important_inputs = list(filter(is_important_path, main_rule.inputs))
            important_outputs = list(filter(is_important_path, main_rule.outputs))
            # print("main_rule:", main_rule.argv[0])
            # print("  important cmd:", is_important_cmd(main_rule.argv))
            # print("  ", list(filter(is_important_path, main_rule.inputs)))
            # print("  ", list(filter(is_important_path, main_rule.outputs)))
            if is_important_cmd(main_rule.argv) or important_inputs or important_outputs:
                # print("  keep")
                child_rules = []
                # We want to take main_rule, but we need to subsume all child rules
                for child_exec_pair in networkx.descendants(exec_pair_graph, curr_exec_pair):
                    # print("  child:", all_rules[child_exec_pair].argv[0])
                    child_rules.append(all_rules[child_exec_pair])
                main_rule = Rule.combine(main_rule, child_rules).filter(is_important_path)
                doubled_paths = frozenset(main_rule.inputs) & frozenset(main_rule.outputs)
                main_rule = main_rule.filter(lambda path: path not in doubled_paths).deduplicate()
                rules.append(main_rule)
                traversal.send(False)
            else:
                # print("  ditch")
                traversal.send(True)
        else:
            traversal.send(True)
    return rules


def to_source(
        workflow_type: WorkflowType,
        directory: pathlib.Path,
        rules: It[Rule],
        include_env: bool,
) -> None:
    {
        WorkflowType.SNAKEMAKE: to_snakemake
    }[workflow_type](directory, rules, include_env)


def to_snakemake(
        directory: pathlib.Path,
        rules: It[Rule],
        include_env: bool
) -> None:
    lines = []
    lines.append(b"# Generated by PROBE")
    for rule in rules:
        lines.append(b"rule " + rule.argv[0] + b"_" + str(hash(rule)).encode() + b":")
        lines.append(b"  input:")
        for input in rule.inputs:
            lines.append(b"    \"" + str(input).encode() + b"\"")
        lines.append(b"  output:")
        for output in rule.outputs:
            lines.append(b"    \"" + str(output).encode() + b"\"")
        lines.append(b"  shell:")
        lines.append(b"    " + repr(shlex.join([
            "env",
            "--chdir",
            str(rule.cwd),
            *([env.decode() for env in rule.env] if include_env else []),
            *(argv.decode() for argv in rule.argv)
        ])).encode())
    lines.append(b"")
    (directory / "Snakefile").write_bytes(b"\n".join(lines))


def get_exec_pair_graph(probe_log: ptypes.ProbeLog) -> networkx.DiGraph[ptypes.ExecPair]:
    graph: networkx.DiGraph[ptypes.ExecPair] = networkx.DiGraph()
    for quad, op in probe_log.ops():
        current = quad.exec_pair()
        graph.add_node(current)
        if isinstance(op.data, ops.CloneOp) and op.data.task_type == ptypes.TaskType.TASK_PID and op.data.ferrno == 0:
            target = ptypes.ExecPair(
                ptypes.Pid(op.data.task_id),
                ptypes.ExecNo(0),
            )
            graph.add_edge(current, target)
        elif isinstance(op.data, ops.SpawnOp) and op.data.ferrno == 0:
            target = ptypes.ExecPair(
                ptypes.Pid(op.data.child_pid),
                ptypes.ExecNo(0),
            )
            graph.add_edge(current, target)
        elif isinstance(op.data, ops.ExecOp) and op.data.ferrno == 0:
            target = ptypes.ExecPair(
                quad.pid,
                ptypes.ExecNo(quad.exec_no + 1),
            )
            graph.add_edge(current, target)
    return graph
