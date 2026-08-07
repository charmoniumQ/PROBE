from collections.abc import Iterable as It, Mapping as Map
import fnmatch
import getpass
import pathlib
import shlex
import warnings
import zlib
import rdflib
import rdflib.container
import rdflib.term
import rdflib.namespace
import prov.model  # type: ignore
from . import dataflow_graph
from . import headers
from . import ptypes


RDF = rdflib.namespace.RDF
RDFS = rdflib.namespace.RDFS
PROV = rdflib.namespace.PROV
AD_HOC_NAMESPACE = rdflib.Namespace("http://example.org/to-be-formalized/#")
PROV_LABEL = rdflib.URIRef("http://www.w3.org/ns/prov#label")


type Agent = rdflib.term.Node
type Activity = rdflib.term.Node
type Entity = rdflib.term.Node


def export_rdf_graph(
        probe_log: ptypes.ProbeLog,
        analysis: dataflow_graph.Analysis,
        dfg: dataflow_graph.DataflowGraph,
        ignore_paths: It[str],
        include_paths: It[str],
) -> tuple[rdflib.Graph, prov.model.ProvDocument]:
    graph = rdflib.Graph()
    graph.bind("rdf", RDF)
    graph.bind("ad_hoc", AD_HOC_NAMESPACE)

    # TODO: Get username at record-time
    user = add_user(graph)

    child_to_ancestor = get_child_to_ancestor(analysis)

    exec_to_activity = add_processes(probe_log, analysis, child_to_ancestor, graph, user)

    inode_to_entity = add_inodes(analysis, dfg, graph, ignore_paths, include_paths)

    ivn_to_term = add_inode_versions(analysis, dfg, inode_to_entity, graph, user)

    add_edges(dfg, ivn_to_term, exec_to_activity, graph)

    for subject, label in graph.subject_objects(RDFS.label):
        graph.add((subject, PROV_LABEL, label))

    graph_serialized = graph.serialize(format="turtle")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The following attributes were not converted",
            category=UserWarning,
        )
        prov_document = prov.model.ProvDocument.deserialize(
            content=graph_serialized,
            format="rdf",
            rdf_format="turtle",
        )

    return graph, prov_document


def get_child_to_ancestor(
        analysis: dataflow_graph.Analysis
) -> Map[ptypes.Pid, ptypes.ExecPair]:
    ret = {}
    for parent, child in analysis.clones:
        assert child.pid not in ret
        ret[child.pid] = parent.exec_pair()
    return ret


def add_processes(
        probe_log: ptypes.ProbeLog,
        analysis: dataflow_graph.Analysis,
        child_to_ancestor: Map[ptypes.Pid, ptypes.ExecPair],
        graph: rdflib.Graph,
        user: Agent,
) -> Map[ptypes.ExecPair, Activity]:
    exec_to_activity = dict[ptypes.ExecPair, Activity]()
    root_pid = probe_log.get_root_pid()
    for pid, process in probe_log.processes.items():
        for exec_no, exec in process.execs.items():
            # If exec_no = 0, we could be a multiprocessing program (fork but no exec)
            # Find the ancestor who was execked.
            ancestor_exec_pair = ptypes.ExecPair(pid, exec_no)
            while ancestor_exec_pair.exec_no == 0 and ancestor_exec_pair.pid != root_pid:
                ancestor_exec_pair = child_to_ancestor[ancestor_exec_pair.pid]

            # Found the ancestor who was execked.
            # Make sure they have an activity
            activity: Activity
            if ancestor_exec_pair not in exec_to_activity:
                print(ancestor_exec_pair, "is true exec")
                init_exec_op = probe_log.processes[ancestor_exec_pair.pid].execs[ancestor_exec_pair.exec_no].threads[ancestor_exec_pair.pid.main_thread()].ops[0].data
                assert isinstance(init_exec_op, headers.InitExecEpoch), init_exec_op
                arg_list = rdflib.container.Seq(graph, rdflib.BNode(), [
                    rdflib.Literal(arg.decode())
                    for arg in init_exec_op.argv
                ])  # type: ignore
                activity = exec_to_activity[ancestor_exec_pair] = rdflib.URIRef(f"exec_{ancestor_exec_pair.pid}_{ancestor_exec_pair.exec_no}")
                graph.add((activity, RDF.type, PROV.Activity))
                graph.add((activity, PROV.wasAssociatedWith, user))
                graph.add((activity, RDF.type, AD_HOC_NAMESPACE.OSProcess))
                graph.add((activity, AD_HOC_NAMESPACE.arguments, arg_list.uri))
                graph.add((activity, AD_HOC_NAMESPACE.environment_hash, rdflib.Literal(hash_environment(init_exec_op.env))))
                graph.add((activity, RDFS.label, rdflib.Literal(shlex.join([arg.decode() for arg in init_exec_op.argv]))))
            else:
                activity = exec_to_activity[ancestor_exec_pair]

            # Set my activity to theirs, up the tree.
            # We don't know the order PIDs will be assigned in (can't assume sequential), so we may have to do our grandancestors.
            ultimate_ancestor_exec_pair = ancestor_exec_pair
            ancestor_exec_pair = ptypes.ExecPair(pid, exec_no)
            while ancestor_exec_pair.exec_no == 0 and ancestor_exec_pair.pid != root_pid:
                print(ancestor_exec_pair, "was forked from", ultimate_ancestor_exec_pair)
                if ancestor_exec_pair not in exec_to_activity:
                    exec_to_activity[ancestor_exec_pair] = activity
                ancestor_exec_pair = child_to_ancestor[ancestor_exec_pair.pid]

    return exec_to_activity


def hash_environment(environment: It[bytes]) -> int:
    seed = 0x12345678
    for value in environment:
        seed = zlib.adler32(value, seed)
    return seed


def add_inodes(
        analysis: dataflow_graph.Analysis,
        dfg: dataflow_graph.DataflowGraph,
        graph: rdflib.Graph,
        ignore_paths: It[str],
        include_paths: It[str],
) -> Map[ptypes.Inode, tuple[pathlib.Path | None, int, rdflib.term.Node]]:
    device_to_term = dict[ptypes.Device, rdflib.term.Node]()
    inode_to_term = dict[ptypes.Inode, tuple[pathlib.Path | None, int, rdflib.term.Node]]()
    path_to_inode_to_major_version = dict[pathlib.Path, dict[ptypes.Inode, int]]()
    for node in sorted(dfg.nodes(), key=node_sorter):
        if isinstance(node, dataflow_graph.IVNs):
            for ivn in sorted(node):
                device = ivn.inode.device
                if device not in device_to_term:
                    device_term = rdflib.URIRef(f"device_{device.major_id}_{device.minor_id}")
                    graph.add((device_term, RDFS.label, rdflib.Literal(f"device {device.major_id}_{device.minor_id}")))
                    graph.add((device_term, RDF.type, AD_HOC_NAMESPACE.OSFileSystemDevice))
                    graph.add((device_term, AD_HOC_NAMESPACE.major_id, rdflib.Literal(device.major_id)))
                    graph.add((device_term, AD_HOC_NAMESPACE.minor_id, rdflib.Literal(device.minor_id)))
                    device_to_term[device] = device_term
                inode = ivn.inode
                if inode not in inode_to_term:
                    path_counter = analysis.paths[ivn.inode]
                    representative_path: pathlib.Path | None
                    if path_counter:
                        include = all(
                            not fnmatch.fnmatch(str(path), ignore_path)
                            for path in path_counter
                            for ignore_path in ignore_paths
                        ) or any(
                            fnmatch.fnmatch(str(path), include_path)
                            for path in path_counter
                            for include_path in include_paths
                        )
                        max_path_count = max(path_counter.values())
                        max_paths = [
                            path
                            for path, count in path_counter.items()
                            if count == max_path_count
                        ]
                        representative_path = min(max_paths, key=lambda path: path.parts)
                        inode_to_major_version = path_to_inode_to_major_version.setdefault(representative_path, dict())
                        major_version = inode_to_major_version.setdefault(inode, len(inode_to_major_version) + 1)
                    else:
                        representative_path = None
                        major_version = inode.number
                        include = True
                    if include:
                        inode_term = rdflib.URIRef(f"inode_{device.major_id}_{device.minor_id}_{inode.number}")
                        graph.add((inode_term, RDF.type, AD_HOC_NAMESPACE.OSInode))
                        if representative_path is not None:
                            graph.add((inode_term, RDFS.label, rdflib.Literal(f"{representative_path!s} v{major_version}")))
                        else:
                            graph.add((inode_term, RDFS.label, rdflib.Literal(f"<anonymous path {major_version}>")))
                        graph.add((inode_term, AD_HOC_NAMESPACE.device, device_to_term[device]))
                        graph.add((inode_term, AD_HOC_NAMESPACE.number, rdflib.Literal(inode.number)))
                        for path_obj, _ in analysis.paths[ivn.inode].most_common():
                            path2 = rdflib.container.Seq(graph, rdflib.BNode(), [
                                rdflib.Literal(segment)
                                for segment in path_obj.parts
                            ])  # type: ignore
                            graph.add((path2.uri, RDF.type, AD_HOC_NAMESPACE.OSFilePath))
                            graph.add((inode_term, AD_HOC_NAMESPACE.has_path, path2.uri))
                            # graph.add((inode_term, AD_HOC_NAMESPACE.has_path, rdflib.Literal(str(path_obj))))
                        inode_to_term[inode] = (representative_path, major_version, inode_term)                        
    return inode_to_term


def node_sorter(node: dataflow_graph.IVNs | dataflow_graph.Quads) -> tuple[int, int, int, int, int]:
    match node:
        case dataflow_graph.IVNs():
            representative = min(node)
            return (0, representative.inode.device.major_id, representative.inode.device.minor_id, representative.inode.number, representative.version)
        case dataflow_graph.Quads():
            representative_quad = min(node)
            return (1, int(representative_quad.pid), int(representative_quad.exec_no), int(representative_quad.tid), int(representative_quad.op_no))
        case _:
            raise TypeError()


def add_inode_versions(
        analysis: dataflow_graph.Analysis,
        dfg: dataflow_graph.DataflowGraph,
        inode_to_entity: Map[ptypes.Inode, tuple[pathlib.Path | None, int, rdflib.term.Node]],
        graph: rdflib.Graph,
        user: Agent,
) -> Map[dataflow_graph.InodeVersionNode, Entity]:
    ivn_to_entity = {}
    for node in dfg.nodes():
        if isinstance(node, dataflow_graph.IVNs):
            for ivn in node:
                if ivn.inode in inode_to_entity:
                    representative_path, major_version, inode_term = inode_to_entity[ivn.inode]
                    ivn_to_entity[ivn] = entity = rdflib.URIRef(f"inodeversion_{ivn.inode.device.major_id}_{ivn.inode.device.minor_id}_{ivn.inode.number}_{ivn.version}")
                    graph.add((entity, RDF.type, PROV.Entity))
                    graph.add((entity, RDF.type, AD_HOC_NAMESPACE.OSInodeVersion))
                    if representative_path is not None:
                        graph.add((entity, RDFS.label, rdflib.Literal(f"{representative_path!s} v{major_version}.{ivn.version}")))
                    else:
                        graph.add((entity, RDFS.label, rdflib.Literal(f"<anonymous path {major_version} v{ivn.version}>")))
                    graph.add((entity, AD_HOC_NAMESPACE.inode, inode_term))
                    graph.add((entity, AD_HOC_NAMESPACE.version, rdflib.Literal(ivn.version)))
                    graph.add((entity, PROV.wasAttributedTo, user))
    return ivn_to_entity


def add_edges(
        dfg: dataflow_graph.DataflowGraph,
        ivn_to_entity: Map[dataflow_graph.InodeVersionNode, Entity],
        exec_to_activity: Map[ptypes.ExecPair, Activity],
        graph: rdflib.Graph,
) -> None:
    for source, destination, edge_data in dfg.edges(data=True):
        match source, destination:
            case (dataflow_graph.IVNs(), dataflow_graph.IVNs()):
                for source_ivn in source:
                    if source_ivn_term := ivn_to_entity.get(source_ivn):
                        for destination_ivn in destination:
                            if destination_ivn_term := ivn_to_entity.get(destination_ivn):
                                graph.add((destination_ivn_term, PROV.wasRevisionOf, source_ivn_term))
            case (dataflow_graph.IVNs(), dataflow_graph.Quads()):
                activity = exec_to_activity[destination.exec_pair()]
                for source_ivn in source:
                    if source_ivn_term := ivn_to_entity.get(source_ivn):
                        graph.add((activity, PROV.used, source_ivn_term))
            case (dataflow_graph.Quads(), dataflow_graph.IVNs()):
                activity = exec_to_activity[source.exec_pair()]
                for destination_ivn in destination:
                    if destination_ivn_term := ivn_to_entity.get(destination_ivn):
                        graph.add((destination_ivn_term, PROV.wasGeneratedBy, activity))
            case (dataflow_graph.Quads(), dataflow_graph.Quads()):
                source_activity = exec_to_activity[source.exec_pair()]
                destination_activity = exec_to_activity[destination.exec_pair()]
                if edge_data["label"] == dataflow_graph.EdgeType.EXEC:
                    graph.add((source_activity, AD_HOC_NAMESPACE.executed, destination_activity))
                    graph.add((destination_activity, PROV.wasStartedBy, source_activity))


def add_user(graph: rdflib.Graph) -> Agent:
    username = getpass.getuser()
    user = rdflib.URIRef(f"user_{username}")
    graph.add((user, RDF.type, PROV.Agent))
    graph.add((user, RDF.type, AD_HOC_NAMESPACE.OSUser))
    graph.add((user, AD_HOC_NAMESPACE.Username, rdflib.Literal(username)))
    graph.add((user, RDFS.label, rdflib.Literal(username)))
    return user
