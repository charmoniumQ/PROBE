import dataclasses
import enum
import os
import pathlib
import textwrap
import typing
import warnings
import networkx
import tqdm
from . import graph_utils
from . import hb_graph
from . import ops
from . import ptypes


_Node = typing.TypeVar("_Node")


class Access(enum.IntEnum):
    """In what way are we accessing the inode version?"""
    READ = enum.auto()
    WRITE = enum.auto()
    READ_WRITE = enum.auto()
    TRUNCATE_WRITE = enum.auto()


@dataclasses.dataclass(frozen=True)
class AccessEpoch[_Node]:
    """An access epoch is a set of nodes, denoted by a segment, in which the node may be accessed."""
    access: Access
    bounds: graph_utils.Segment[_Node]
    version: int | None = None


@dataclasses.dataclass(frozen=True)
class ExecNode:
    """An exec, denoted by Pid and ExecNo"""
    pid: ptypes.Pid
    exec_no: ptypes.ExecNo


@dataclasses.dataclass(frozen=True)
class InodeVersionNode:
    """A particular version of the inode"""
    inode: ptypes.Inode
    version: int
    paths: frozenset[pathlib.Path]

    def __str__(self) -> str:
        return f"{' '.join(map(str, self.paths))} {self.inode.number} v{self.version}"


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[hb_graph.OpNode | InodeVersionNode]
    CompressedDataflowGraph: typing.TypeAlias = networkx.DiGraph[hb_graph.OpNode | frozenset[InodeVersionNode]]
    EpochGraph: typing.TypeAlias = networkx.DiGraph[AccessEpoch[hb_graph.OpNode]]
else:
    DataflowGraph = networkx.DiGraph
    CompressedDataflowGraph = networkx.DiGraph
    EpochGraph = networkx.DiGraph


def hb_graph_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        hbg: hb_graph.HbGraph,
        copy_hbg: bool,
) -> DataflowGraph:
    if copy_hbg:
        hbg = hbg.copy()

    reduced_hb_graph = hb_graph.retain_only(
        probe_log,
        hbg,
        lambda node, op: isinstance(op.data, (ops.OpenOp, ops.CloseOp, ops.DupOp, ops.ExecOp)) and op.data.ferrno == 0,
    )

    reduced_hb_graph_tc = graph_utils.LazyTransitiveClosure(hbg)

    inode_epochs = get_fine_inode_epochs(
        probe_log,
        reduced_hb_graph,
        reduced_hb_graph_tc,
    )

    dataflow_graph = typing.cast(DataflowGraph, reduced_hb_graph.copy())
    validate_dataflow_graph(probe_log, dataflow_graph)

    for inode, epochs in tqdm.tqdm(inode_epochs.items(), "inodes"):
        epoch_graph = graph_utils.hasse_diagram(
            epochs,
            lambda node0, node1: not reduced_hb_graph_tc.non_ancestors(
                node1.bounds.upper_bound,
                node0.bounds.lower_bound,
            ),
        )

        sorted_epochs = list(networkx.topological_sort(epoch_graph))

        reads, writes = number_sorted_epochs(sorted_epochs)

        check_for_races(epoch_graph, reads, writes)

        add_nodes(probe_log, dataflow_graph, inode, reads, writes)

        validate_dataflow_graph(probe_log, dataflow_graph)

    return dataflow_graph


def reduce_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: DataflowGraph,
) -> DataflowGraph:
    reduced_dataflow_graph = DataflowGraph()
    reduced_nodes = dict[tuple[ptypes.Pid, ptypes.ExecNo], hb_graph.OpNode]()
    accepting_reads = dict[tuple[ptypes.Pid, ptypes.ExecNo], bool]()
    for node in networkx.topological_sort(dataflow_graph):
        if isinstance(node, hb_graph.OpNode):
            key = (node.pid, node.exec_no)
            if key not in reduced_nodes:
                reduced_nodes[key] = node
                accepting_reads[key] = True
                print("root", node)
            op_predecessors = [
                predecessor
                for predecessor in dataflow_graph.predecessors(node)
                if isinstance(predecessor, hb_graph.OpNode) and not _is_program_order(predecessor, node)
            ]
            op_successors = [
                successor
                for successor in dataflow_graph.successors(node)
                if isinstance(successor, hb_graph.OpNode) and not _is_program_order(successor, node)
            ]
            inode_predecessors = [
                predecessor
                for predecessor in dataflow_graph.predecessors(node)
                if isinstance(predecessor, InodeVersionNode)
            ]
            inode_successors = [
                successor
                for successor in dataflow_graph.successors(node)
                if isinstance(successor, InodeVersionNode)
            ]
            if inode_predecessors or op_predecessors:
                if not accepting_reads[key]:
                    reduced_dataflow_graph.add_edge(reduced_nodes[key], node)
                    print(reduced_nodes[key], node)
                    accepting_reads[key] = True
                    reduced_nodes[key] = node
                for inode_predecessor in inode_predecessors:
                    reduced_dataflow_graph.add_edge(
                        inode_predecessor,
                        reduced_nodes[key],
                    )
                for op_predecessor in op_predecessors:
                    # We used to consider op predecessors like "reads" of inodes.
                    # But that could introduce cycles in the dataflow graph.
                    # The predecessor themselves could have had conflicting operations.
                    # Consider the program:
                    #     fork.
                    #     If parent: wait on child.
                    #     If child: write file foo.
                    # Naively, our graph would have main_0 -> child, main_0 -> main_1, child -> main_1
                    reduced_dataflow_graph.add_edge(
                        reduced_nodes[(op_predecessor.pid, op_predecessor.exec_no)],
                        reduced_nodes[key],
                    )
            if op_successors or inode_successors:
                accepting_reads[key] = False
                # In the old DFG, this node (this proc) -> target_node (other proc)
                # But in the reduced DFG, we don't know the target_node yet,
                # because we don't know how the other proc is being reduced.
                # So we can't create this edge right now.
                # But we should switch out of accepting reads, as this is functionally a write.
                # The edge will get created by the target_node's op_predecessors logic.
                for inode_successor in inode_successors:
                    reduced_dataflow_graph.add_edge(reduced_nodes[key], inode_successor)
    return reduced_dataflow_graph


def combine_indistinguishable_inodes(
        dataflow_graph: DataflowGraph,
) -> CompressedDataflowGraph:
    def same_neighbors(
            node0: hb_graph.OpNode | InodeVersionNode,
            node1: hb_graph.OpNode | InodeVersionNode,
    ) -> bool:
        return (
            isinstance(node0, InodeVersionNode)
            and
            isinstance(node1, InodeVersionNode)
            and
            frozenset(dataflow_graph.predecessors(node0)) == frozenset(dataflow_graph.predecessors(node1))
            and
            frozenset(dataflow_graph.successors(node0)) == frozenset(dataflow_graph.successors(node1))
        )
    def node_mapper(node_set: frozenset[hb_graph.OpNode | InodeVersionNode]) -> hb_graph.OpNode | frozenset[InodeVersionNode]:
        first_node = next(iter(node_set))
        if isinstance(first_node, hb_graph.OpNode):
            assert all(isinstance(node, hb_graph.OpNode) for node in node_set)
            return first_node
        else:
            assert all(isinstance(node, InodeVersionNode) for node in node_set)
            return typing.cast(frozenset[InodeVersionNode], node_set)

    return graph_utils.map_nodes(
        node_mapper,
        networkx.quotient_graph(dataflow_graph, same_neighbors),
    )


def _is_program_order(
        node0: hb_graph.OpNode | InodeVersionNode,
        node1: hb_graph.OpNode | InodeVersionNode,
) -> bool:
    return isinstance(node0, hb_graph.OpNode) and isinstance(node1, hb_graph.OpNode) and node0.pid == node1.pid and node0.exec_no == node1.exec_no


def get_fine_inode_epochs(
        probe_log: ptypes.ProbeLog,
        hbg: hb_graph.HbGraph,
        hbg_tc: graph_utils.LazyTransitiveClosure[hb_graph.OpNode],
) -> typing.Mapping[ptypes.Inode, typing.Sequence[AccessEpoch[hb_graph.OpNode]]]:
    """Return a mapping from inode to a list of each segment during which an indoe can be accessed."""

    out = dict[ptypes.Inode, list[AccessEpoch[hb_graph.OpNode]]]()

    for node in tqdm.tqdm(hbg.nodes(), "file nodes"):
        op = probe_log.get_op(*node.op_quad())
        if isinstance(op.data, ops.OpenOp) and op.data.ferrno == 0:
            inode_version = ptypes.InodeVersion.from_probe_path(op.data.path)
            access_mode = op.data.flags & os.O_ACCMODE
            closes = frozenset(_find_closes(
                probe_log,
                hbg,
                node,
                op.data.fd,
                bool(op.data.flags & os.O_CLOEXEC),
            ))

            # needed for dup ops
            # Consider the program: int fd = open("foo", O_RDONLY); fd2 = dup(fd); close(fd); close(fd2);
            # This would have two closes: fd2 and fd.
            # We only care about the bottommost.
            # It's "nicer" if the bounds of the intervals form antichains (otherwise they contain redundancy).
            # So we will filter for only the bottommost closes.
            bottommost_closes = hbg_tc.get_bottommost(closes)

            segment = graph_utils.Segment(
                hbg_tc,
                frozenset({node}),
                bottommost_closes,
            )
            if access_mode == os.O_RDONLY:
                access = Access.READ
            elif op.data.flags & (os.O_TRUNC | os.O_CREAT):
                access = Access.TRUNCATE_WRITE
            elif access_mode == os.O_WRONLY:
                access = Access.WRITE
            elif access_mode == os.O_RDWR:
                access = Access.READ_WRITE
            else:
                raise ptypes.InvalidProbeLog(
                    f"Found file {op.data.path.path.decode()} with invalid access mode"
                )
        elif isinstance(op.data, ops.ExecOp) and op.data.ferrno == 0:
            access = Access.READ
            inode_version = ptypes.InodeVersion.from_probe_path(op.data.path)
            segment = graph_utils.Segment(hbg_tc, frozenset({node}), frozenset({node}))
        else:
            inode_version = None
            segment = None
            access = None

        if segment:
            assert inode_version
            assert access
            out.setdefault(inode_version.inode, []).append(AccessEpoch(access, segment))
    return out


def number_sorted_epochs(
        sorted_epochs: list[AccessEpoch[hb_graph.OpNode]],
) -> tuple[list[AccessEpoch[hb_graph.OpNode]], list[AccessEpoch[hb_graph.OpNode]]]:
    reads = []
    writes = list[AccessEpoch[hb_graph.OpNode]]()
    for epoch in sorted_epochs:
        epoch = dataclasses.replace(epoch, version=len(writes))
        if epoch.access == Access.READ:
            reads.append(epoch)
        if epoch.access != Access.READ:
            writes.append(epoch)
    return reads, writes


def check_for_races(
        epoch_graph_tc: EpochGraph,
        reads: list[AccessEpoch[hb_graph.OpNode]],
        writes: list[AccessEpoch[hb_graph.OpNode]],
) -> typing.Iterator[tuple[AccessEpoch[hb_graph.OpNode], AccessEpoch[hb_graph.OpNode]]]:
    for write0, write1 in zip(writes[:-1], writes[1:]):
        if write0 not in epoch_graph_tc.predecessors(write1):
            yield (write0, write1)

    for read in reads:
        assert read.version
        if read.access == Access.READ:
            if read.version > 0:
                write_before = writes[read.version - 1]
                if write_before not in epoch_graph_tc.predecessors(read):
                    yield (read, write_before)
            if read.version < len(writes):
                write_after = writes[read.version]
                if write_after not in epoch_graph_tc.successors(read):
                    yield (read, write_before)


def add_nodes(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: DataflowGraph,
        inode: ptypes.Inode,
        reads: list[AccessEpoch[hb_graph.OpNode]],
        writes: list[AccessEpoch[hb_graph.OpNode]],
) -> None:
    # need_v0 = (reads and reads[0].version == 0) or (writes and writes[0].access in {Access.READ_WRITE, Access.WRITE})

    paths = set[pathlib.Path]()
    for epoch in [*reads, *writes]:
        for node in [*epoch.bounds.upper_bound, *epoch.bounds.lower_bound]:
            op_data = probe_log.get_op(*node.op_quad()).data
            match op_data:
                case ops.ExecOp() | ops.OpenOp() | ops.CloseOp():
                    paths.add(pathlib.Path(op_data.path.path.decode(errors="backslashreplace")))
    frozen_paths = frozenset(paths)

    for epoch in [*reads, *writes]:
        assert epoch.version is not None
        version = InodeVersionNode(inode, epoch.version, frozen_paths)
        next_version = InodeVersionNode(inode, epoch.version + 1, frozen_paths)
        match epoch.access:
            case Access.WRITE:
                for op_node in epoch.bounds.lower_bound:
                    dataflow_graph.add_edge(op_node, next_version)
                dataflow_graph.add_edge(version, next_version)
            case Access.TRUNCATE_WRITE:
                for op_node in epoch.bounds.lower_bound:
                    dataflow_graph.add_edge(op_node, next_version)
            case Access.READ_WRITE:
                for op_node in epoch.bounds.upper_bound:
                    dataflow_graph.add_edge(version, op_node)
                for op_node in epoch.bounds.lower_bound:
                    dataflow_graph.add_edge(op_node, next_version)
            case Access.READ:
                for op_node in epoch.bounds.upper_bound:
                    dataflow_graph.add_edge(version, op_node)


def label_nodes(probe_log: ptypes.ProbeLog, dataflow_graph: DataflowGraph) -> None:
    count = dict[tuple[ptypes.Pid, ptypes.ExecNo], int]()
    for node in networkx.topological_sort(dataflow_graph):
        data = dataflow_graph.nodes(data=True)[node]
        match node:
            case hb_graph.OpNode():
                if node.op_no == 0:
                    count[(node.pid, node.exec_no)] = 1
                    if node.exec_no != 0:
                        op = probe_log.get_op(node.pid, node.exec_no, node.pid.main_thread(), 0)
                        assert isinstance(op.data, ops.InitExecEpochOp)
                        data["label"] = "exec\n" + "\n".join(
                            textwrap.shorten(
                                arg.decode(errors="backslashreplace"),
                                width=100,
                            )
                            for arg in op.data.argv[:10]
                        ) + ("\n..." if len(op.data.argv) > 10 else "")
                    else:
                        data["label"] = "(child proc)"
                else:
                    data["label"] = f"proc v{count[(node.pid, node.exec_no)]}"
                    count[(node.pid, node.exec_no)] += 1
                data["shape"] = "oval"
            case InodeVersionNode():
                def shorten_path(input: pathlib.Path) -> str:
                    return ("/" if input.is_absolute() else "") + "/".join(
                        textwrap.shorten(part, width=20)
                        for part in input.parts
                        if part != "/"
                    )
                data["label"] = f"{' '.join(map(shorten_path, node.paths))} v{node.version}"
                data["shape"] = "rectangle"

    for node0, node1, data in dataflow_graph.edges(data=True):
        if isinstance(node0, hb_graph.OpNode) and isinstance(node1, hb_graph.OpNode) and node0.pid != node1.pid:
            data["style"] = "dashed"

    # dataflow_graph_tc = graph_utils.add_self_loops(networkx.transitive_closure(dataflow_graph), False)
    # inode_to_last_node: dict[ptypes.Inode, None | InodeVersionNode] = {
    #     node.inode: None
    #     for node in dataflow_graph.nodes()
    #     if isinstance(node, InodeVersionNode)
    # }
    # for node in networkx.topological_sort(dataflow_graph):
    #     if isinstance(node, InodeVersionNode):
    #         if last_node := inode_to_last_node.get(node.inode):
    #             if last_node.version + 1 == node.version:
    #                 if not any(
    #                         writer in dataflow_graph_tc.predecessors(node)
    #                         for writer in dataflow_graph.predecessors(last_node)
    #                 ):
    #                     raise ptypes.InvalidProbeLog(f"We incremented versions to {node.version}, but there is no path from {last_node} to {node}")
    # TODO


def validate_dataflow_graph(
        probe_log: ptypes.ProbeLog,
        dataflow_graph: DataflowGraph,
        # dataflow_graph_tc: DataflowGraph | None,
) -> None:
    # if dataflow_graph_tc is None:
    #     dataflow_graph_tc = graph_utils.add_self_loops(networkx.transitive_closure(dataflow_graph), False)
    # TODO
    # if not networkx.is_directed_acyclic_graph(dataflow_graph):
    #     cycle = list(networkx.find_cycle(dataflow_graph))
    #     output = pathlib.Path("invalid.dot").resolve()
    #     label_nodes(probe_log, dataflow_graph)
    #     graph_utils.serialize_graph(dataflow_graph, output)
    #     raise ptypes.InvalidProbeLog(f"Found a cycle in graph: {cycle}; see {output}")

    if not networkx.is_weakly_connected(dataflow_graph):
        warnings.warn(f"Graph is not strongly connected: {'\n'.join(map(str, networkx.weakly_connected_components(dataflow_graph)))}")

    # inode_to_last_node: dict[ptypes.Inode, None | InodeVersionNode] = {
    #     node.inode: None
    #     for node in dataflow_graph.nodes()
    #     if isinstance(node, InodeVersionNode)
    # }
    # TODO
    # for node in networkx.topological_sort(dataflow_graph):
    #     if isinstance(node, InodeVersionNode):
    #         if last_node := inode_to_last_node.get(node.inode):
    #             if last_node.version + 1 == node.version:
    #                 if not any(
    #                         writer in dataflow_graph_tc.predecessors(node)
    #                         for writer in dataflow_graph.predecessors(last_node)
    #                 ):
    #                     pass
    #                     #raise ptypes.InvalidProbeLog(f"We incremented versions to {node.version}, but there is no path from {last_node} to {node}")
    #             else:
    #                 if last_node.version != node.version:
    #                     raise ptypes.InvalidProbeLog(f"We went from {last_node.version} to {node.version}")
    #         else:
    #             if node.version not in {0, 1}:
    #                 raise ptypes.InvalidProbeLog(f"Version of an initial access should be 0 or 1 not {node.version} ")
    #         inode_to_last_node[node.inode] = node
        # TODO: Check CloseOp and OpenOp
        # OpenOp.path should match CloseOp.path


def _find_closes(
        probe_log: ptypes.ProbeLog,
        hbg: hb_graph.HbGraph,
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
                    ret |= _find_closes(probe_log, hbg, successor, op.data.new, cloexec)
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
                    ret |= _find_closes(probe_log, hbg, target, fd, cloexec)

        # Either this op closes the file OR we need to add your children to the frontier
        if is_closed:
            ret.add(node)
        else:
            successors_with_op_data = [
                (successor, probe_log.get_op(*successor.op_quad()).data)
                for successor in hbg.successors(node)
            ]
            child_or_same_proc_successors = [
                successor
                for successor, op_data in successors_with_op_data
                # If this process gets joined by its parent,
                # the parent shouldn't be able to see the fds opened by this process.
                if successor.pid == node.pid or isinstance(op_data, ops.CloneOp)
            ]
            if child_or_same_proc_successors:
                for successor in child_or_same_proc_successors:
                    frontier.append(successor)
            else:
                # We reached a node with no successor;
                # This is functionally a close
                ret.add(node)

    return ret
