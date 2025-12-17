from __future__ import annotations
import collections.abc
import dataclasses
import datetime
import getpass
import enum
import itertools
import pathlib
import shlex
import shutil
import subprocess
import typing
import networkx
import rdflib

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
    WRROC = enum.auto()


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
        WorkflowType.SNAKEMAKE: to_snakemake,
        WorkflowType.WRROC: to_wrroc,
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


def to_wrroc(
        directory: pathlib.Path,
        rules: It[Rule],
        include_env: bool
) -> None:
    all_files = set()
    def get_bnode(file: pathlib.Path) -> rdflib.Node:
        all_files.add(file)
        return rdflib.URIRef("file://" + str(file))
        # id = files.setdefault(entity.name, {}).setdefault(entity, len(files[entity.name]))
        # return rdflib.URIRef(f"file-{entity.name}" + "" if id == 0 else f"-{id}")
    envs = {}
    softwares = set()
    directories = set()
    graph = rdflib.Graph()
    schemaorg = rdflib.namespace.Namespace("http://schema.org/")
    dct = rdflib.namespace.Namespace("http://purl.org/dc/terms/")
    prov = rdflib.namespace.Namespace("http://www.w3.org/ns/prov#")
    rdf = rdflib.namespace.RDF
    custom = rdflib.namespace.Namespace("http://example.com/")
    nfo = rdflib.namespace.Namespace("https://www.semanticdesktop.org/ontologies/2007/03/22/nfo/#")
    wfprov = rdflib.namespace.Namespace("http://purl.org/wf4ever/wfprov#")
    foaf = rdflib.namespace.FOAF
    graph.bind("schemaorg", schemaorg)
    graph.bind("dct", dct)
    graph.bind("prov", prov)
    graph.bind("rdf", rdf)
    graph.bind("custom", custom)
    graph.bind("nfo", nfo)
    graph.bind("wfprov", wfprov)
    graph.bind("foaf", foaf)
    username = getpass.getuser()
    agent = rdflib.BNode(f"user-{username}")
    graph.add((agent, rdf.type, foaf.Agent))
    graph.add((agent, rdf.type, prov.Agent))
    graph.add((agent, foaf.name, rdflib.Literal(username)))
    for i, rule in enumerate(rules):
        softwares.add(rule.exe)
        env_hash = hash(frozenset(rule.env))
        envs[env_hash] = rule.env
        action = rdflib.BNode(f"action-{rule.exe.name}-{i}")
        graph.add((action, rdf.type, schemaorg.CreateAction))
        graph.add((action, rdf.type, prov.activity))
        graph.add((action, rdf.type, wfprov.ProcessRun))
        # TODO:  prov:startedAtTime , prov:endedAtTime
        graph.add((action, schemaorg.description, rdflib.Literal(shlex.join(argv.decode() for argv in rule.argv))))
        graph.add((action, schemaorg.instrument, get_bnode(rule.exe)))
        graph.add((action, wfprov.wasInitiatedBy, agent))
        graph.add((action, prov.wasAssociatedWith, agent))
        softwares.add(rule.exe)
        if rule.cwd is not None:
            graph.add((action, custom.cwd, get_bnode(pathlib.Path(rule.cwd))))
            directories.add(rule.cwd)
        for entity in rule.inputs:
            graph.add((action, prov.used, get_bnode(entity)))
            graph.add((action, schemaorg.object, get_bnode(entity)))
            graph.add((action, wfprov.usedInput, get_bnode(entity)))
        for entity in rule.outputs:
            graph.add((action, prov.generated, get_bnode(entity)))
            graph.add((action, schemaorg.result, get_bnode(entity)))
            graph.add((action, wfprov.wasOutputFrom, get_bnode(entity)))

    for file in all_files:
        bnode = get_bnode(file)
        graph.add((bnode, rdf.type, prov.Entity))
        if file in softwares:
            graph.add((bnode, rdf.type, schemaorg.SoftwareApplication))
            graph.add((bnode, rdf.type, nfo.Executable))
        elif file in directories:
            graph.add((bnode, rdf.type, schemaorg.Collection))
            graph.add((bnode, rdf.type, nfo.Folder))
        else:
            graph.add((bnode, rdf.type, schemaorg.MediaObject))
            graph.add((bnode, rdf.type, nfo.FileDataObject))
            graph.add((bnode, rdf.type, wfprov.Artifact))
        graph.add((bnode, schemaorg.name, rdflib.Literal(str(file.name))))
        graph.add((bnode, nfo.fileName, rdflib.Literal(str(file.name))))
        file_bin = shutil.which("file")
        # TODO: do this at probe record time.
        # TODO: Put in user/agent info
        if file.exists():
            if file_bin:
                graph.add((
                    bnode,
                    nfo.encoding,
                    rdflib.Literal(subprocess.run([file_bin, "--mime-encoding", "--brief", file], check=True, capture_output=True, text=True).stdout.strip()),
                ))
                graph.add((
                    bnode,
                    nfo.encoding,
                    rdflib.Literal(subprocess.run([file_bin, "--mime-type", "--brief", file], check=True, capture_output=True, text=True).stdout.strip()),
                ))
            file_stat = file.stat()
            graph.add((bnode, nfo.fileLastModified, rdflib.Literal(datetime.datetime.fromtimestamp(file_stat.st_mtime))))
            graph.add((bnode, nfo.fileSize, rdflib.Literal(file_stat.st_size)))
            # TODO: prov creation date

    graph.serialize("ro-crate-metadata.json", format="json-ld")
    graph.serialize("ro-crate-metadata.xml", format="xml")
    graph.serialize("ro-crate-metadata.ttl", format="ttl")
    # relevant_owls = [
    #     "https://www.w3.org/ns/prov-o",
    #     # not really that useful
    #     # See https://www.semanticarts.com/dublin-core-and-owl/
    #     "https://protege.stanford.edu/plugins/owl/dc/terms.owl",
    #     "https://schema.org/docs/schemaorg.owl",
    # ]
    # relevant_shacls = [
    #     "https://raw.githubusercontent.com/schemaorg/schemaorg/refs/heads/main/data/releases/29.3/schemaorg-shapes.shacl"
    # ]
    # relevent_shexjs = [
    #     "https://github.com/schemaorg/schemaorg/blob/main/data/releases/29.3/schemaorg-shapes.shexj"
    # ]


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
