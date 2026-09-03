from __future__ import annotations
import pathlib
import shlex
import typing
import msgspec
import networkx
from . import dataflow_graph
from . import graph_utils
from . import headers
from . import ptypes


class Workflow(msgspec.Struct, frozen=True):
    rules: list[Rule]


class Rule(msgspec.Struct, frozen=True):
    outputs: list[pathlib.Path]
    inputs: list[pathlib.Path]
    command: list[str]
    exe: pathlib.Path


def workflowize(
        probe_log: ptypes.ProbeLog,
        analysis: dataflow_graph.Analysis,
        dfg: dataflow_graph.DataflowGraph,
) -> Workflow:
    # ivn_to_node = util.groupby_dict_single(
    #     [
    #         (ivn, node)
    #         for node in dfg.nodes()
    #         if isinstance(node, dataflow_graph.IVNs)
    #         for ivn in node
    #     ],
    #     lambda pair: pair[0],
    #     lambda pair: pair[1],
    #     lambda ivn, nodes: ptypes.InvalidProbeLog(f"{ivn} seen in multiple IVNs nodes {nodes}; perhaps error in DFG ivn compression"),
    # )

    # inode_to_ivn = util.groupby_dict_single(
    #     [
    #         (ivn.inode, ivn)
    #         for ivn in ivn_to_node.keys()
    #     ],
    #     lambda pair: pair[0],
    #     lambda pair: pair[1],
    #     lambda inode, ivns: ValueError(f"{inode} was mutated, has multiple ivns {ivns}, which makes this graph not workflow-izable"),
    # )

    # # Each path should map from only one inode
    # # Otherwise, it is mutated, and it is unclear which version applise
    # path_to_inode = util.groupby_dict_single(
    #     [
    #         (path, inode)
    #         for inode, path_counter in analysis.paths.items()
    #         for path in path_counter
    #     ],
    #     lambda pair: pair[0],
    #     lambda pair: pair[1],
    #     lambda path, inodes: ValueError(f"{path} maps to multiple inodes {inodes}, meaning the path was deleted and re-created, not workflow-izable"),
    # )

    # path_to_node = {
    #     path: ivn_to_node[inode_to_ivn[inode]]
    #     for path, inode in path_to_inode.items()
    # }
    node_to_path = {
        node: [
            path
            for ivn in node
            for path in analysis.paths[ivn.inode]
        ]
        for node in dfg.nodes()
        if isinstance(node, dataflow_graph.IVNs)
    }

    pid_to_exe = {}
    pid_to_command = {}
    root_pid = analysis.probe_log.get_root_pid()
    for pid, process in probe_log.processes.items():
        second_exec = ptypes.ExecNo(ptypes.initial_exec_no + 1)
        if pid == root_pid:
            op = process.execs[ptypes.initial_exec_no].threads[pid.main_thread()].ops[0]
            # Should be guaranteed by the structure of the probe log
            assert isinstance(op.data, headers.InitExecEpoch)
            pid_to_command[pid] = op.data.argv
            name = op.data.exe.name
            assert name
            pid_to_exe[pid] = pathlib.Path(name.decode())
        elif second_exec in process.execs:
            op = process.execs[second_exec].threads[pid.main_thread()].ops[0]
            # Should be guaranteed by the structure of the probe log
            assert isinstance(op.data, headers.InitExecEpoch)
            pid_to_command[pid] = op.data.argv
            name = op.data.exe.name
            assert name
            pid_to_exe[pid] = pathlib.Path(name.decode())

    child_to_exec_parent = dict[ptypes.Pid, ptypes.Pid]()
    pid_graph = graph_utils.create_digraph(
        probe_log.processes.keys(),
        [
            (parent.pid, child.pid)
            for parent, child in analysis.clones
        ]
    )
    child_to_exec_parent[root_pid] = root_pid
    for parent, child in networkx.bfs_edges(pid_graph, root_pid):
        assert parent in child_to_exec_parent
        if child not in pid_to_command:
            child_to_exec_parent[child] = child_to_exec_parent[parent]
        else:
            child_to_exec_parent[child] = child

    pid_to_nodes = dict[ptypes.Pid, list[dataflow_graph.Quads]]()
    for node in dfg.nodes():
        if isinstance(node, dataflow_graph.Quads):
            for quad in node:
                if (int(quad.exec_no) >= 1 or quad.pid == root_pid) and (exec_parent := child_to_exec_parent.get(quad.pid)):
                    pid_to_nodes.setdefault(exec_parent, []).append(node)

    rules = []
    for pid, nodes in pid_to_nodes.items():
        inputs = set()
        outputs = set()
        for node in nodes:
            for predecessor in dfg.predecessors(node):
                if isinstance(predecessor, dataflow_graph.IVNs):
                    for path in node_to_path[predecessor]:
                        inputs.add(path)
            for successor in dfg.successors(node):
                if isinstance(successor, dataflow_graph.IVNs) and not any(
                        dfg.get_edge_data(successor, grand_successor, default={}).get("label") == dataflow_graph.EdgeType.FILE_CLOBBER
                        for grand_successor in dfg.successors(successor)
                ):
                    for path in node_to_path[successor]:
                        outputs.add(path)

        if outputs:
            rules.append(Rule(
                command=[
                    arg.decode()
                    for arg in pid_to_command[pid]
                ],
                inputs=list(inputs),
                outputs=list(outputs),
                exe=pid_to_exe[pid],
            ))

    return Workflow(rules)


def serialize_yaml(workflow: Workflow, output: pathlib.Path) -> None:
    output.write_bytes(msgspec.yaml.encode(workflow, enc_hook=msgspec_enc_hook))


def serialize_makefile(workflow: Workflow, makefile: pathlib.Path) -> None:
    makefile = makefile.resolve()
    with makefile.open("w+") as fobj:
        for rule in workflow.rules:
            assert rule.outputs
            fobj.write(" ".join([
                str(path.relative_to(makefile.parent) if path.is_relative_to(makefile.parent) else path)
                for path in rule.outputs
            ]))
            fobj.write(": ")
            fobj.write(" ".join([
                str(path.relative_to(makefile.parent) if path.is_relative_to(makefile.parent) else path)
                for path in rule.inputs
            ]))
            fobj.write("\n\t")
            fobj.write(shlex.join(rule.command))
            fobj.write("\n\n")


def msgspec_enc_hook(obj: typing.Any) -> typing.Any:
    if isinstance(obj, pathlib.Path):
        return str(obj)
    raise NotImplementedError


def msgspec_dec_hook(type_: type[typing.Any], obj: typing.Any) -> typing.Any:
    if type_ is pathlib.Path:
        return pathlib.Path(obj)
    return obj
