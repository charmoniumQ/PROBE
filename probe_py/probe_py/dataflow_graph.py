import dataclasses
import enum
import functools
import os
import typing
import networkx
import shlex
import warnings
from .ptypes import Inode, InodeVersion, InvalidProbeLog, ProbeLog
from . import ops
from . import hb_graph
from . import process_tree
from . import graph_utils


@dataclasses.dataclass(frozen=True)
class InodeVersionNode:
    inode: Inode
    version: int


@dataclasses.dataclass(frozen=True)
class OpSegment:
    """A set of upper bounds and a set of lower bounds.

    The Segment contains all the nodes in either bound and between the bounds.
    """
    upper_bound: frozenset[hb_graph.OpNode]
    lower_bound: frozenset[hb_graph.OpNode]


class Access(enum.IntEnum):
    READ = enum.auto()
    WRITE = enum.auto()
    READ_WRITE = enum.auto()
    TRUNCATE_WRITE = enum.auto()


DfNode: typing.TypeAlias = hb_graph.OpNode | InodeVersionNode


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[DfNode]
else:
    DataflowGraph = networkx.DiGraph


def hb_graph_to_dataflow_graph(
        probe_log: ProbeLog,
        hbg: hb_graph.HbGraph,
        copy_hbg: bool,
) -> DataflowGraph:
    if copy_hbg:
        hbg = hbg.copy()

    reduced_hb_graph = hb_graph.retain_only(
        probe_log,
        hbg,
        lambda node, op: isinstance(op.data, (ops.OpenOp, ops.CloseOp, ops.DupOp, ops.ExecOp)),
    )

    inode_access_segments = get_inode_access_segments(
        probe_log,
        reduced_hb_graph,
    )

    dataflow_graph = typing.cast(DataflowGraph, reduced_hb_graph)
    validate_dataflow_graph(dataflow_graph, False)

    inode_versions: typing.Mapping[Inode, list[InodeVersionNode]] = {
        inode: []
        for inode, _, _ in inode_access_segments
    }

    # At first, we give each file access a distniguishing version number
    # Then we will sew together the inode versions that should be identical
    # This number needs to be one greater than the greatest possible number of writes + 1
    # Later on, we will use 0...len(writes)+1 as the version number
    n_nodes = len(list(dataflow_graph.nodes())) + 1
    for inode, access, segment in inode_access_segments:
        add_segment(n_nodes, dataflow_graph, inode_versions, inode, access, segment)
        validate_dataflow_graph(dataflow_graph, False)

    dataflow_tc = graph_utils.add_self_loops(networkx.transitive_closure(dataflow_graph), False)

    for inode, versions in inode_versions.items():
        # The writes will be totally ordered OR we have a possible data race.
        ordered_write_nodes = totally_order_writes(
            dataflow_graph,
            dataflow_tc,
            inode,
            versions,
        )
        reannotate_versions(
            dataflow_graph,
            inode,
            versions,
            ordered_write_nodes,
        )
        validate_dataflow_graph(dataflow_graph, False)
        # dataflow_graph has been mutated, but it will be consistent with the old one.

    validate_dataflow_graph(dataflow_graph, True)

    # Transitive reduction eliminates unnecessary dataflow edges
    dataflow_graph = networkx.transitive_reduction(dataflow_graph)

    return dataflow_graph


def get_inode_access_segments(
        probe_log: ProbeLog,
        hbg: hb_graph.HbGraph,
) -> list[tuple[Inode, Access, OpSegment]]:
    """Return a list showing each segment of ops during which an indoe can be accessed."""


    ref_trans_closure = graph_utils.add_self_loops(
        networkx.transitive_closure(hbg),
        copy=False,
    )

    proc_tree = process_tree.hb_graph_to_process_tree(probe_log, hbg)

    out = []

    for i, node in enumerate(hbg.nodes()):
        op = probe_log.get_op(*node.op_quad())
        if isinstance(op.data, ops.OpenOp) and op.data.ferrno == 0:
            inode_version = InodeVersion.from_probe_path(op.data.path)
            access_mode = op.data.flags & os.O_ACCMODE
            # open flags O_CLOEXEC
            # clone flags CLONE_FILES
            # TODO: dups
            closes = _find_closes(
                probe_log,
                hbg,
                proc_tree,
                node,
                op.data.fd,
                bool(op.data.flags & os.O_CLOEXEC),
            )
            segment = OpSegment(frozenset({node}), frozenset(closes))
            if access_mode == os.O_RDONLY:
                access = Access.READ
            elif op.data.flags & (os.O_TRUNC | os.O_CREAT):
                access = Access.TRUNCATE_WRITE
            elif access_mode == os.O_WRONLY:
                access = Access.WRITE
            elif access_mode == os.O_RDWR:
                access = Access.READ_WRITE
            else:
                raise InvalidProbeLog(
                    f"Found file {op.data.path.path.decode()} with invalid access mode"
                )
        elif isinstance(op.data, ops.ExecOp) and op.data.ferrno == 0:
            inode_version = InodeVersion.from_probe_path(op.data.path)
            segment = OpSegment(frozenset({node}), frozenset({node}))
            access = Access.READ
        else:
            inode_version = None
            segment = None
            access = None

        if segment:
            assert inode_version
            assert access

            out.append((inode_version.inode, access, segment))

            if not graph_utils.is_valid_segment(
                    ref_trans_closure,
                    segment.upper_bound,
                    segment.lower_bound,
            ):
                raise InvalidProbeLog(f"We created an improper segment {segment}")

    return out


def add_segment(
        n_nodes: int,
        dataflow_graph: DataflowGraph,
        inode_versions: typing.Mapping[Inode, list[InodeVersionNode]],
        inode: Inode,
        access: Access,
        segment: OpSegment,
) -> None:
    """Adds an access to an inode over a segment.

    dataflow_graph and inode_versions are in/out parameters. The rest are in parameters.

    The new nodes we add will begin numbering from n_nodes. The versions below
    n_nodes are considered "reserved" for something else.

    """
    inode_version = InodeVersionNode(
        inode,
        len(inode_versions[inode]) + n_nodes,
    )
    inode_versions[inode].append(inode_version)
    assert not dataflow_graph.has_node(inode_version)
    match access:
        case Access.READ:
            for upper_bound in segment.upper_bound:
                # The actual read can happen any time between upper and lower bound
                # But assuming no data races,
                # We can pretend that it gets read entirely at the earliest possible moment
                # So it influences the most possible ops
                dataflow_graph.add_edge(inode_version, upper_bound)
        case Access.WRITE | Access.READ_WRITE:
            # Likewise, we can assume the write happens at the very lower bound
            # So the most possible ops influence it
            for upper_bound in segment.upper_bound:
                dataflow_graph.add_edge(inode_version, upper_bound)
            new_inode_version = InodeVersionNode(
                inode,
                len(inode_versions[inode]) + n_nodes,
            )
            for lower_bound in segment.lower_bound:
                dataflow_graph.add_edge(lower_bound, new_inode_version)
        case Access.TRUNCATE_WRITE:
            # Unlike WRITE or READ_WRITE, the prior version does not contribute
            for lower_bound in segment.lower_bound:
                dataflow_graph.add_edge(lower_bound, inode_version)


def totally_order_writes(
        dataflow_graph: DataflowGraph,
        dataflow_graph_tc: DataflowGraph,
        inode: Inode,
        versions: list[InodeVersionNode],
) -> list[tuple[list[DfNode], InodeVersionNode]]:
    """Return a list of totally-ordered writes.

    Each write consists of the antichain of nodes which execute (and therefore
    preceed) the write, and the InodeVersionNode which *is written to*.

    dataflow_graph is an in/out parameter.

    """
    write_nodes = [
        (
            list(dataflow_graph.predecessors(ivn)), # anti-chain of write nodes
            ivn, # associated write
        )
        for ivn in versions
        if dataflow_graph.predecessors(ivn)
    ]
    def cmp(
            node0: tuple[list[DfNode], InodeVersionNode],
            node1: tuple[list[DfNode], InodeVersionNode],
    ) -> bool:
        return graph_utils.antichain_prior(
            dataflow_graph_tc,
            node0[0],
            node1[0],
        )
    write_nodes = sorted(
        write_nodes,
        key=functools.cmp_to_key(cmp),
    )

    if write_nodes:
        for (antichain0, ivn0), (antichain1, ivn1) in zip(write_nodes[:-1], write_nodes[1:]):
            if not graph_utils.antichain_prior(dataflow_graph_tc, antichain0, antichain1):
                warnings.warn(f"Appears to be datarace between {ivn0} and {ivn1}")
            if graph_utils.antichain_prior(dataflow_graph_tc, antichain1, antichain0):
                warnings.warn(f"Appears to be datarace between {ivn0} and {ivn1}")

    return write_nodes


def reannotate_versions(
        dataflow_graph: DataflowGraph,
        inode: Inode,
        versions: list[InodeVersionNode],
        ordered_write_nodes: list[tuple[list[DfNode], InodeVersionNode]],
) -> None:
    """Re-annotate versions for each InodeVersionNode according to which write is immediately prior.

    The version-number 0 will be used for the inode before the execution of the program.

    The version-numbers will then fall in the range from 1 to (len(ordered_write_nodes) + 1), inclusive-exclusive.
    """

    write_node_to_version: typing.Mapping[DfNode, int] = {
        node: write_no + 1
        for write_no, write in enumerate(ordered_write_nodes)
        for node in write[0]
    }

    for version in versions:
        # find the nearest preceeding write node
        for upstream_node in networkx.bfs_predecessors(dataflow_graph, version):
            if version_no := write_node_to_version.get(upstream_node):
                break
        else:
            # No prceeding write found.
            # Must be read at the beginning of the program
            version_no = 0

        graph_utils.replace(
            dataflow_graph,
            version,
            InodeVersionNode(
                version.inode,
                version_no,
            ),
        )


def label_nodes(probe_log: ProbeLog, dataflow_graph: DataflowGraph) -> None:
    for node, data in dataflow_graph.nodes(data=True):
        match node:
            case InodeVersionNode():
                paths = []
                for other in [
                        *dataflow_graph.predecessors(node),
                        *dataflow_graph.successors(node),
                ]:
                    if isinstance(other, hb_graph.OpNode):
                        op = probe_log.get_op(*other.op_quad())
                        match op.data:
                            case ops.OpenOp():
                                paths.append(op.data.path.path.decode(errors="backslashreplace"))
                            case ops.ExecOp():
                                paths.append(op.data.path.path.decode(errors="backslashreplace"))
                data["label"] = f"{', '.join(paths)} v{node.version}"
            case hb_graph.OpNode():
                op = probe_log.get_op(*node.op_quad())
                match op.data:
                    case ops.InitExecEpochOp():
                        data["label"] = "exec " + shlex.join(arg.decode(errors="backslashreplace") for arg in op.data.argv)
                    case _:
                        data["label"] = type(op.data).__name__


def validate_dataflow_graph(
        dataflow_graph: DataflowGraph,
        check_version_order: bool,
) -> None:
    if not networkx.is_directed_acyclic_graph(dataflow_graph):
        cycle = list(networkx.find_cycle(dataflow_graph))
        raise InvalidProbeLog(f"Found a cycle in graph: {cycle}")

    if not networkx.is_weakly_connected(dataflow_graph):
        raise InvalidProbeLog(f"Graph is not strongly connected: {list(networkx.weakly_connected_components(dataflow_graph))}")

    if check_version_order:
        inode_to_last_node: dict[Inode, None | InodeVersionNode] = {
            node.inode: None
            for node in dataflow_graph.nodes()
            if isinstance(node, InodeVersionNode)
        }
        dataflow_graph_tc = networkx.transitive_closure(dataflow_graph)
        for node in networkx.topological_sort(dataflow_graph):
            if isinstance(node, InodeVersionNode):
                if last_node := inode_to_last_node.get(node.inode):
                    if last_node.version + 1 == node.version:
                        if not any(
                                writer in dataflow_graph_tc.predecessors(node)
                                for writer in dataflow_graph.predecessors(last_node)
                        ):
                            raise InvalidProbeLog(f"We incremented versions to {node.version}, but there is no path from {last_node} to {node}")
                    else:
                        if last_node.version != node.version:
                            raise InvalidProbeLog(f"We went from {last_node.version} to {node.version}")
                else:
                    if node.version not in {0, 1}:
                        raise InvalidProbeLog(f"Version of an initial access should be 0 or 1 not {node.version} ")
                inode_to_last_node[node.inode] = node
        # TODO: Check CloseOp and OpenOp
        # OpenOp.path should match CloseOp.path


def _find_closes(
        probe_log: ProbeLog,
        hbg: hb_graph.HbGraph,
        proc_tree: process_tree.ProcessTree,
        starting_node: hb_graph.OpNode,
        fd: int,
        cloexec: bool,
) -> set[hb_graph.OpNode]:
    ret = set[hb_graph.OpNode]()
    frontier = [starting_node]
    while frontier:
        node = frontier.pop()
        op = probe_log.get_op(*node.op_quad())
        is_closed = False
        match op.data:
            case ops.CloseOp():
                is_closed = op.data.fd == fd
                # While this closes it for the entire process
                # we don't know the relative ordering between this node and the others in the frontier.
                # They others may have actually happened before, so we will continue tracing those.
            case ops.ExecOp():
                # implicitly closes when the cloexec flag is present
                is_closed = cloexec
            case ops.DupOp():
                for successor in hbg.successors(node):
                    ret |= _find_closes(probe_log, hbg, proc_tree, successor, op.data.new, cloexec)
            case ops.CloneOp():
                # If CLONE_FILES is set, the calling process and the child
                # process share the same file descriptor table.  Any file
                # descriptor created by the calling process or by the child
                # process is also valid in the other process.
                # --- https://www.man7.org/linux/man-pages/man2/close.2.html
                #
                # If this flag is NOT set, we will ahve to close it in this process
                # AND close it in our child process, separately.
                #
                if not op.data.flags & os.CLONE_FILES:
                    target = next(
                        successor
                        for successor in hbg.successors(node)
                        if successor.tid != node.tid
                    )
                    ret |= _find_closes(probe_log, hbg, proc_tree, target, fd, cloexec)

        # Either this op closes the file OR we need to add your children to the frontier
        if is_closed:
            ret.add(node)
        else:
            successors = [
                successor
                for successor in hbg.successors(node)
                # If this process gets joined by its parent,
                # the parent shouldn't be able to see the fds opened by this process.
                if successor.pid == node.pid or successor.pid in set(networkx.descendants(proc_tree, node.pid)) and successor != node
            ]
            if successors:
                for successor in successors:
                    frontier.append(successor)
            else:
                # We reached a node with no successor;
                # This is functionally a close
                ret.add(node)

    return ret
