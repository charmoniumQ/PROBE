from __future__ import annotations
import itertools
import dataclasses
import enum
import os
import pathlib
import typing
import networkx
from .ptypes import Inode, InodeVersion, InvalidProbeLog
from .ops import Op, CloneOp, ExecOp, OpenOp, CloseOp, DupOp
from .hb_graph import HbGraph, OpNode


@dataclasses.dataclass(frozen=True)
class ProcessNode:
    pid: int
    cmd: tuple[str,...]


@dataclasses.dataclass(frozen=True)
class FileAccess:
    inode_version: InodeVersion
    path: pathlib.Path

    @property
    def label(self) -> str:
        return f"{self.path!s} inode {self.inode_version.inode}"


if typing.TYPE_CHECKING:
    DataflowGraph: typing.TypeAlias = networkx.DiGraph[FileAccess | ProcessNode]
else:
    DataflowGraph = networkx.DiGraph


def inode_access_segments(hb_graph: HbGraph) -> list[tuple[Inode, Access, OpSegment]]:
    """Return a list showing each segment of ops during which an indoe can be accessed."""

    out = []

    for node in hb_graph.nodes():
        if isinstance(node.op.data, OpenOp) and node.op.data.ferrno == 0:
            inode_version = InodeVersion.from_probe_path(node.op.data.path)
            access_mode = node.op.data.flags & os.O_ACCMODE
            # open flags O_CLOEXEC
            # clone flags CLONE_FILES
            # TODO: dups
            closes = _find_closes(hb_graph, node, node.op.data.fd, bool(node.op.data.flags & os.O_CLOEXEC))
            segment = OpSegment(frozenset({node}), frozenset(closes))
            if access_mode == os.O_RDONLY:
                out.append((inode_version.inode, Access.READ, segment))
            elif node.op.data.flags & (os.O_TRUNC | os.O_CREAT):
                out.append((inode_version.inode, Access.TRUNCATE_WRITE, segment))
            elif access_mode == os.O_WRONLY:
                out.append((inode_version.inode, Access.WRITE, segment))
            elif access_mode == os.O_RDWR:
                out.append((inode_version.inode, Access.READ_WRITE, segment))
            else:
                raise InvalidProbeLog(
                    f"Found file {node.op.data.path.path.decode()} with invalid access mode"
                )
        elif isinstance(node.op.data, ExecOp) and node.op.data.ferrno == 0:
            inode_version = InodeVersion.from_probe_path(node.op.data.path)
            segment = OpSegment(frozenset({node}), frozenset({node}))
            out.append((inode_version.inode, Access.READ, segment))

    return out


def construct_fine_grain_graph(hb_graph: HbGraph):
    inode_access_segments = inode_access_segments(hb_graph)
    important_nodes = frozenset(itertools.chain.from_iterable(
        segment.upper_bound_inclusive | segment.lower_bound_inclusive
        for _, _, segments in inode_access_segments
    ))


def _find_closes(hb_graph: HbGraph, starting_node: OpNode, fd: int, cloexec: bool) -> set[OpNode]:
    ret = set[OpNode]()
    frontier = [starting_node]
    while frontier:
        node = frontier.pop()
        is_closed = False
        match node.op.data:
            case CloseOp():
                is_closed = node.op.data.fd == fd
                # While this closes it for the entire process
                # we don't know the relative ordering between this node and the others in the frontier.
                # They others may have actually happened before, so we will continue tracing those.
            case ExecOp():
                # implicitly closes when the cloexec flag is present
                is_closed = cloexec
            case DupOp():
                for successor in hb_graph.successors(node):
                    ret |= _find_closes(hb_graph, successor, node.op.data.new, cloexec)
            case CloneOp():
                # If CLONE_FILES is set, the calling process and the child
                # process share the same file descriptor table.  Any file
                # descriptor created by the calling process or by the child
                # process is also valid in the other process.
                # --- https://www.man7.org/linux/man-pages/man2/close.2.html
                #
                # If this flag is NOT set, we will ahve to close it in this process
                # AND close it in our child process, separately.
                #
                if not node.op.data.flags & os.CLONE_FILES:
                    target = next(
                        successor
                        for successor in hb_graph.successors(node)
                        if successor.tid != node.tid
                    )
                    ret |= _find_closes(hb_graph, target, fd, cloexec)

        # Either this op closes the file OR we need to add your children to the frontier
        if is_closed:
            ret.add(node)
        else:
            for successor in hb_graph.successors(node):
                frontier.append(node)


@dataclasses.dataclass(frozen=True)
class OpSegment:
    """A set of upper bounds and a set of lower bounds.

    The Segment contains all the nodes in either bound and between the bounds.
    """
    upper_bound_inclusive: frozenset[OpNode]
    lower_bound_inclusive: frozenset[OpNode]


class Access(enum.IntEnum):
    READ = enum.auto()
    WRITE = enum.auto()
    READ_WRITE = enum.auto()
    TRUNCATE_WRITE = enum.auto()
