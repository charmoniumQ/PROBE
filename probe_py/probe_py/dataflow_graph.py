from __future__ import annotations
from collections.abc import Mapping as Map, Iterable as It
import collections
import dataclasses
import enum
import fnmatch
import heapq
import pathlib
import shlex
import textwrap
import typing
import warnings
import charmonium.time_block
import networkx
import tqdm
from . import graph_utils
from . import hb_graph as hb_graph_mod
from . import headers
from . import partial_order
from . import ptypes
from . import util
from . import vector_clock


class State(int):
    pass


@dataclasses.dataclass(frozen=True, order=True)
class ExecState:
    pid: ptypes.Pid
    exec_no: ptypes.ExecNo
    state_id: State


@dataclasses.dataclass(frozen=True, order=True)
class InodeVersionNode:
    """A particular version of the inode"""

    inode: ptypes.Inode
    version: int

    def __str__(self) -> str:
        return f"{self.inode} version {self.version}"


# make these new classes, so I can use isinstance
class IVNs(frozenset[InodeVersionNode]):
    pass


class Quads(frozenset[ptypes.OpQuad]):
    def exec_pair(self) -> ptypes.ExecPair:
        pairs = self.exec_pairs()
        if len(pairs) == 1:
            return next(iter(pairs))
        else:
            raise ValueError(f"Quad contains multiple exec pairs {pairs}")

    def thread_triple(self) -> ptypes.ThreadTriple:
        triples = self.thread_triples()
        if len(triples) == 1:
            return next(iter(triples))
        else:
            raise ValueError(f"Quad contains multiple thread triples {triples}")

    def thread_triples(self) -> frozenset[ptypes.ThreadTriple]:
        return frozenset({quad.thread_triple() for quad in self})

    def exec_pairs(self) -> frozenset[ptypes.ExecPair]:
        return frozenset({quad.exec_pair() for quad in self})


type UncompressedDataflowGraph = networkx.DiGraph[ptypes.OpQuad | InodeVersionNode]
type DataflowGraph = networkx.DiGraph[Quads | IVNs]
type NodeData = dict[str, typing.Any]


CUTOFF: typing.Final[int] = 4


@charmonium.time_block.decor(print_start=False)
def hb_graph_to_dataflow_graph(
    probe_log: ptypes.ProbeLog,
    hb_graph: hb_graph_mod.HbGraph,
    verbose: bool,
    loose: bool,
    conservative: bool,
) -> tuple[Analysis, DataflowGraph]:
    dfg: UncompressedDataflowGraph = networkx.DiGraph()
    analysis = Analysis.init(probe_log, hb_graph, verbose, loose, conservative)
    inode_intervals = find_intervals(analysis)
    print(
        f"{len(inode_intervals)} inodes, {sum(len(intervals) for intervals in inode_intervals.values())} intervals"
    )
    top_k = heapq.nlargest(
        10, ((len(intervals), inode) for inode, intervals in inode_intervals.items())
    )
    if top_k and top_k[0] and top_k[0][0] > CUTOFF:
        print(f"Top inodes with more than {CUTOFF} intervals:")
        for len_inode_intervals, inode in top_k:
            if len_inode_intervals < 5:
                break
            print(f"  {len_inode_intervals} {inode}")
    for inode, intervals in tqdm.tqdm(
        inode_intervals.items(),
        total=len(inode_intervals),
        desc="Inode intervals to stitch",
    ):
        if all(path.parts[1] not in {"dev", "proc", "sys"} for path in analysis.paths[inode]):
            stitch_intervals(dfg, analysis, inode, intervals)
    with charmonium.time_block.ctx(name="stitch other", print_start=False):
        root_pid = analysis.probe_log.get_root_pid()
        first_quad = ptypes.OpQuad(root_pid, ptypes.initial_exec_no, root_pid.main_thread(), 0)
        dfg.add_node(first_quad)
        stitch_threads(dfg, analysis)
        for exec_quad, target in analysis.execs:
            dfg.add_edge(exec_quad, target, label=EdgeType.EXEC)
        for clone_quad, target in analysis.clones:
            dfg.add_edge(clone_quad, target, label=EdgeType.FORK)
        stitch_program_order(dfg, analysis)
    compressed_dfg = compress(analysis, dfg, verbose)
    return analysis, compressed_dfg


class EdgeType(enum.StrEnum):
    THREAD = enum.auto()
    PROGRAM_ORDER = enum.auto()
    EXEC = enum.auto()
    FORK = enum.auto()
    FILE = enum.auto()


def stitch_threads(dfg: UncompressedDataflowGraph, analysis: Analysis) -> None:
    for node in analysis.hb_graph.nodes():
        # Find peers of me that are NOT peers of my successors
        # If I don't put an arrow from me to that peer, none of my successors will be able to.
        # I should put it to the highest peer that meets the condition.
        highest_peers = {
            peer for peer in analysis.highest_peers[node] if peer.exec_pair() == node.exec_pair()
        } - {
            peer
            for pred in analysis.hb_graph.successors(node)
            for peer in analysis.highest_peers[pred]
        }
        for highest_peer in highest_peers:
            dfg.add_edge(node, highest_peer, label=EdgeType.THREAD)


def stitch_program_order(dfg: UncompressedDataflowGraph, analysis: Analysis) -> None:
    threads: dict[ptypes.ThreadTriple, list[ptypes.OpQuad]] = {}
    for node in dfg.nodes():
        if isinstance(node, ptypes.OpQuad):
            threads.setdefault(node.thread_triple(), []).append(node)
    for nodes in threads.values():
        nodes = sorted(nodes, key=lambda quad: quad.op_no)
        for node0, node1 in zip(nodes[:-1], nodes[1:]):
            dfg.add_edge(node0, node1, label=EdgeType.PROGRAM_ORDER)


@dataclasses.dataclass
class OpenNumberInfo:
    order: vector_clock.VectorClockPartialOrder[ptypes.OpQuad, ptypes.ThreadTriple]
    inode: ptypes.Inode
    open: ptypes.OpQuad
    open_mode: ptypes.AccessMode
    close_bound: vector_clock.VectorTime | None = None
    closes: list[tuple[ptypes.OpQuad, ptypes.AccessMode | None]] = dataclasses.field(
        default_factory=list
    )

    def add_close(self, quad: ptypes.OpQuad, mode: ptypes.AccessMode | None) -> None:
        self.closes.append((quad, mode))
        closes = self.order.lower_bounds(close for close, _ in self.closes)
        self.close_bound = vector_clock.upper_bound(
            [self.order.vector_clocks[close] for close in closes]
        )

    def is_open(self, quad: ptypes.OpQuad) -> bool:
        before_the_open = not (self.open <= quad)
        after_all_closes = (
            self.close_bound <= self.order.vector_clocks[quad]
            if self.close_bound is not None
            else False
        )
        if not before_the_open and not after_all_closes:
            return self._expensive_is_open(quad)
        return not before_the_open and not after_all_closes

    def _expensive_is_open(self, quad: ptypes.OpQuad) -> bool:
        return not any(self.order.leq(close, quad) for close, _ in self.closes)


@dataclasses.dataclass
class Analysis:
    # TODO: Have fewer variables here, especially when tracking the mapping from open number to items.
    probe_log: ptypes.ProbeLog
    hb_graph: hb_graph_mod.HbGraph
    order: vector_clock.VectorClockPartialOrder[ptypes.OpQuad, ptypes.ThreadTriple]
    highest_peers: Map[
        ptypes.OpQuad,
        frozenset[ptypes.OpQuad],
    ]
    sources: set[ptypes.OpQuad]
    verbose: bool
    loose: bool
    conservative: bool
    open_numbers: dict[
        ptypes.ExecPair,
        dict[
            int,
            dict[
                int,
                OpenNumberInfo,
            ],
        ],
    ] = dataclasses.field(
        default_factory=lambda: collections.defaultdict(lambda: collections.defaultdict(dict))
    )
    last: dict[ptypes.Pid, ptypes.OpQuad] = dataclasses.field(default_factory=dict)
    execs: list[tuple[ptypes.OpQuad, ptypes.OpQuad]] = dataclasses.field(default_factory=list)
    clones: list[tuple[ptypes.OpQuad, ptypes.OpQuad]] = dataclasses.field(default_factory=list)
    paths: dict[ptypes.Inode, collections.Counter[pathlib.Path]] = dataclasses.field(
        default_factory=lambda: collections.defaultdict(collections.Counter)
    )

    @charmonium.time_block.decor(print_start=True)
    @staticmethod
    def init(
        probe_log: ptypes.ProbeLog,
        hb_graph: hb_graph_mod.HbGraph,
        verbose: bool,
        loose: bool,
        conservative: bool,
    ) -> Analysis:
        with charmonium.time_block.ctx("vector clocks", print_start=False):
            order = vector_clock.from_dag(hb_graph, lambda node: node.thread_triple())
            print(f"Diameter of HBG: {order.diameter()}")
        with charmonium.time_block.ctx("highest_peers", print_start=True):
            highest_peers = partial_order.highest_peers(order, hb_graph)
        return Analysis(
            probe_log=probe_log,
            hb_graph=hb_graph,
            order=order,
            highest_peers=highest_peers,
            sources=set(graph_utils.get_sources(hb_graph)),
            verbose=verbose,
            loose=loose,
            conservative=conservative,
        )

    @charmonium.time_block.decor(print_start=True)
    def __post_init__(self) -> None:
        ptc = self.probe_log.process_tree_context
        first_quad = graph_utils.get_sources(self.hb_graph)[0]
        initial_open_number = 0
        for ops_inode, fd, path, access_mode in [
            (ptc.std_in, 0, "/dev/stdin", ptypes.AccessMode.READ),
            (ptc.std_out, 1, "/dev/stdout", ptypes.AccessMode.WRITE),
            (ptc.std_err, 2, "/dev/stderr", ptypes.AccessMode.WRITE),
            (
                ptc.working_directory_inode,
                headers.AT_FDCWD,
                bytes(ptc.working_directory).decode().strip(),
                ptypes.AccessMode.DIRECTORY,
            ),
        ]:
            inode = ptypes.Inode.from_ops_inode(ops_inode)
            self.paths[inode][pathlib.Path(path)] += 1
            self.open_numbers[first_quad.exec_pair()][fd][initial_open_number] = OpenNumberInfo(
                order=self.order,
                inode=inode,
                open=first_quad,
                open_mode=access_mode,
            )
            if self.verbose:
                print(f"Initial open {first_quad.exec_pair()}: {fd},0 {inode}")

        total = len(self.hb_graph)
        for quad in tqdm.tqdm(
            networkx.topological_sort(self.hb_graph), total=total, desc="Analysis"
        ):
            data = self.probe_log.get_op(quad).data

            if quad.tid == quad.pid.main_thread():
                self.last[quad.pid] = quad

            open_numbers = self.open_numbers[quad.exec_pair()]

            match data:
                case headers.Open():
                    # Update open_numbers and access mode
                    access_mode = ptypes.AccessMode.from_open_flags(data.flags)
                    inode = ptypes.Inode.from_ops_inode(data.inode)
                    if self.verbose:
                        print(f"Open {quad}: {data.open_number} {inode} {access_mode}")
                    if data.open_number.number == 0:
                        warnings.warn(
                            f"zero open-number should not be used for newly opened files: {quad} {data.open_number} {inode} {access_mode}"
                        )
                        continue
                    assert data.open_number.number not in open_numbers[data.open_number.fd]
                    open_numbers[data.open_number.fd][data.open_number.number] = OpenNumberInfo(
                        order=self.order,
                        inode=inode,
                        open=quad,
                        open_mode=access_mode,
                    )

                    # Close prior open numbers on the same FD
                    # TODO: Enable this without breaking the bank
                    # same_fd_earlier_number_unclosed_onis = [
                    #     oni
                    #     for on, oni in open_numbers[data.open_number.fd].items()
                    #     if on < data.open_number.number and oni.is_open(quad)
                    # ]
                    # for unclosed_oni in same_fd_earlier_number_unclosed_onis:
                    #     unclosed_oni.closes.append((quad, unclosed_oni.open_mode))
                    #     if self.verbose:
                    #         print(f"Close (implicit) {quad}: {data.open_number}")

                    # Handle path names
                    if data.path.name:
                        directory_oni = self.open_numbers[quad.exec_pair()][
                            data.path.directory.fd
                        ].get(data.path.directory.number)
                        if directory_oni is None:
                            warnings.warn(
                                ptypes.UnusualProbeLog(
                                    f"Use of unknown open number as dir exec={quad.exec_pair()}, on={data.path.directory}"
                                )
                            )
                            dir_paths = collections.Counter([pathlib.Path("?")])
                        else:
                            dir_inode = directory_oni.inode
                            maybe_dir_paths = self.paths.get(dir_inode)
                            if maybe_dir_paths is None:
                                warnings.warn(
                                    ptypes.UnusualProbeLog(
                                        f"Unknown directory path for {quad.exec_pair()} {data.path.directory}"
                                    )
                                )
                                dir_paths = collections.Counter([pathlib.Path("?")])
                            else:
                                dir_paths = maybe_dir_paths
                        for dir_path in dir_paths:
                            path_obj = dir_path / data.path.name.decode()
                            assert path_obj.is_absolute()
                            self.paths[inode][path_obj] += 1

                case headers.Close():
                    oni = open_numbers[data.open_number.fd].get(data.open_number.number)
                    if oni is None:
                        pass
                        # Some objects like eventpolls are associated with FDs in a manner we don't track for performance reasons
                        # These will cause "close of unknown open number", and do not represent an error.
                        # warnings.warn(
                        #     ptypes.UnusualProbeLog(
                        #         f"Close of unknown open number quad={quad}, on={data.open_number}, data={data}"
                        #     )
                        # )
                    else:
                        if self.verbose:
                            print(
                                f"Close {quad}: {data.open_number} {oni.inode.number} opened at {oni.open}",
                            )
                        if (
                            self.probe_log.process_tree_context.interpose_read_writes
                            and not self.conservative
                        ):
                            try:
                                downgraded_access = oni.open_mode.downgrade(
                                    data.open_number.is_write, data.open_number.is_read
                                )
                            except ValueError as exc:
                                if self.loose:
                                    downgraded_access = (
                                        (None, ptypes.AccessMode.READ),
                                        (ptypes.AccessMode.WRITE, ptypes.AccessMode.READ_WRITE),
                                    )[data.open_number.is_write][data.open_number.is_read]
                                    string = ("R" if data.open_number.is_read else "") + (
                                        "W" if data.open_number.is_write else ""
                                    )
                                    warnings.warn(
                                        ptypes.UnusualProbeLog(
                                            f"Downgrading {oni.open_mode} to {downgraded_access} due to {string!r} accesses, which should not be possible."
                                        )
                                    )
                                else:
                                    raise exc
                        else:
                            downgraded_access = oni.open_mode
                        oni.closes.append((quad, downgraded_access))

                case headers.Dup():
                    assert data.dst.number, (quad, data)

                    # This dup might be an implicit close.
                    if oni := open_numbers[data.old_dst.fd].get(data.old_dst.number):
                        if (
                            self.probe_log.process_tree_context.interpose_read_writes
                            and not self.conservative
                        ):
                            downgraded_access = oni.open_mode.downgrade(
                                data.old_dst.is_write, data.old_dst.is_read
                            )
                        else:
                            downgraded_access = oni.open_mode
                        oni.closes.append((quad, downgraded_access))
                        if self.verbose:
                            print(f"Close (implicit) {quad}: {data.old_dst} {downgraded_access}")

                    # Close prior open numbers on the same FD
                    same_fd_earlier_number_unclosed_onis2 = [
                        (open_number_obj, oni)
                        for open_number_obj in [data.src, data.dst, data.old_dst]
                        for on, oni in open_numbers[open_number_obj.fd].items()
                        if oni.is_open(quad) and on < open_number_obj.number
                    ]
                    for open_number_obj, oni in same_fd_earlier_number_unclosed_onis2:
                        if self.verbose:
                            print(f"Close (implicit) {quad}: {open_number_obj}")
                        oni.closes.append((quad, oni.open_mode))

                    # dst now points to src
                    oni = open_numbers[data.src.fd].get(data.src.number)
                    if oni is None:
                        warnings.warn(
                            ptypes.UnusualProbeLog(f"Dup of unknown open number {quad} {data.src}")
                        )
                    else:
                        if self.verbose:
                            print(f"Dup {quad}: {data.src}->{data.dst} ({oni.inode})")
                        assert data.dst.number not in open_numbers[data.dst.fd], (
                            f"Open number already used: {quad}, {data.dst.number}"
                        )
                        open_numbers[data.dst.fd][data.dst.number] = OpenNumberInfo(
                            order=self.order,
                            inode=oni.inode,
                            open=quad,
                            open_mode=oni.open_mode,
                        )

                case headers.Clone():
                    if data.task_type == headers.TaskType.PID:
                        # Copy currently-open open_numbers
                        target_pid = ptypes.Pid(data.task_id)
                        target_quad = ptypes.OpQuad(
                            target_pid,
                            ptypes.initial_exec_no,
                            target_pid.main_thread(),
                            0,
                        )
                        self.clones.append((quad, target_quad))
                        for fd, onis in open_numbers.items():
                            for on, oni in onis.items():
                                if oni.is_open(quad):
                                    self.open_numbers[target_quad.exec_pair()][fd][on] = (
                                        OpenNumberInfo(
                                            order=self.order,
                                            inode=oni.inode,
                                            open=target_quad,
                                            open_mode=oni.open_mode,
                                        )
                                    )

                case headers.Exec():
                    # Copy currently-open open_numbers
                    # TODO: could also eliminate when cloexec has been set, but that doesn't matter as much
                    # This would have to be done for:
                    # - open*(..., O_CLOEXEC)
                    # - dup*(..., FD_CLOEXEC)
                    # - fcntl(int fd, F_DUPFD_CLOEXEC/F_DUPFD, int arg)
                    # - fcntl(fd, F_SETFD/F_SETFL)
                    # Conservatively assume not cloexec
                    target_quad = ptypes.OpQuad(
                        quad.pid, quad.exec_no.next(), quad.pid.main_thread(), 0
                    )
                    self.execs.append((quad, target_quad))
                    if self.verbose:
                        print(f"Exec {quad} -> {target_quad}")
                    for fd, onis in open_numbers.items():
                        for on, oni in onis.items():
                            if oni.is_open(quad):
                                if self.verbose:
                                    print(f"  {fd} still open")
                                self.open_numbers[target_quad.exec_pair()][fd][0] = OpenNumberInfo(
                                    order=self.order,
                                    inode=oni.inode,
                                    open=target_quad,
                                    open_mode=oni.open_mode,
                                )

            if all(successor.pid != quad.pid for successor in self.hb_graph.successors(quad)):
                # Last of the PID.
                # Implicitly close all files
                for fd, onis in open_numbers.items():
                    for on, oni in onis.items():
                        if oni.is_open(quad):
                            oni.closes.append((quad, oni.open_mode))


def find_intervals(
    analysis: Analysis,
) -> Map[ptypes.Inode, Map[partial_order.Interval[ptypes.OpQuad], ptypes.AccessMode]]:
    ret: dict[ptypes.Inode, dict[partial_order.Interval[ptypes.OpQuad], ptypes.AccessMode]] = (
        collections.defaultdict(dict)
    )
    for exec, onis_by_fd in analysis.open_numbers.items():
        for fd, onis_by_on in onis_by_fd.items():
            for on, oni in onis_by_on.items():
                if oni.inode.type != "d":
                    closes = util.groupby_dict(
                        oni.closes,
                        key_func=lambda pair: pair[1],
                        value_func=lambda pair: pair[0],
                    )
                    for mode, close_quads in closes.items():
                        if mode:
                            close_quads2 = analysis.order.lower_bounds(close_quads)
                            ret[oni.inode][analysis.order.interval({oni.open}, close_quads2)] = mode
    return ret


def stitch_intervals(
    dfg: UncompressedDataflowGraph,
    analysis: Analysis,
    inode: ptypes.Inode,
    intervals: Map[partial_order.Interval[ptypes.OpQuad], ptypes.AccessMode],
    print_inodes: bool = False,
) -> None:
    source_interval = analysis.order.interval(analysis.sources, analysis.sources)
    intervals = {
        **{key: value for key, value in intervals.items()},
        source_interval: ptypes.AccessMode.WRITE,
    }
    order = analysis.order.interval_order()
    dag = order.hasse_diagram(intervals)
    highest_peers = partial_order.highest_peers(order, dag)
    versions: dict[partial_order.Interval[ptypes.OpQuad], InodeVersionNode] = {}

    for interval in networkx.topological_sort(dag):
        assert len({node.exec_pair() for node in interval.upper_bound}) == 1
        assert len({node.exec_pair() for node in interval.lower_bound}) == 1
        assert {node.exec_pair() for node in interval.lower_bound} == {
            node.exec_pair() for node in interval.upper_bound
        }
        if intervals[interval].can_write:
            versions[interval] = InodeVersionNode(inode, len(versions))
            if interval != source_interval:
                for node in interval.lower_bound:
                    dfg.add_edge(node, versions[interval], label=EdgeType.FILE)
        if print_inodes:
            print(
                "  interval:",
                format_interval(interval),
                intervals[interval].name,
                versions.get(interval),
            )

    if print_inodes:
        for int0, int1 in dag.edges():
            print("  edge:", format_interval(int0), "->", format_interval(int1))

    for write_interval in networkx.topological_sort(dag):
        write_exec_pair = list(write_interval.upper_bound)[0].exec_pair()
        if intervals[write_interval].can_write:
            if print_inodes:
                print(
                    "  write:",
                    format_interval(interval),
                    intervals[write_interval].name,
                    versions[write_interval],
                )
            my_highest_peers = highest_peers[write_interval] | set(dag.successors(write_interval))
            # TODO: highest peer should take a predicate, return the highest peers satisfying the predicate.
            # Maybe it should be the set of peers satisfying the predicate until the first one that doesn't.
            my_highest_peers = order.upper_bounds(my_highest_peers)
            traversal = partial_order.topo_sort_subset(order, dag, my_highest_peers, set())
            for read_interval in traversal:
                assert read_interval
                if print_inodes:
                    print("    write ≤ read:", format_interval(read_interval))
                read_exec_pair = list(read_interval.upper_bound)[0].exec_pair()
                if write_exec_pair == read_exec_pair:
                    # Already in the same exec pair.
                    # Will already be connected by program order or exec edges.
                    traversal.send(True)
                else:
                    if intervals[read_interval].can_read:
                        for dst in read_interval.upper_bound:
                            dfg.add_edge(versions[write_interval], dst, label=EdgeType.FILE)
                        traversal.send(True)
                    elif intervals[read_interval].can_mutate:
                        dfg.add_edge(
                            versions[write_interval],
                            versions[read_interval],
                            label=EdgeType.FILE,
                        )
                        traversal.send(False)
                    elif intervals[read_interval].is_truncating:
                        traversal.send(False)


@charmonium.time_block.decor(print_start=False)
def compress(
    analysis: Analysis,
    dfg: UncompressedDataflowGraph,
    verbose: bool,
) -> DataflowGraph:
    dfg_old = trivial_compress(dfg)

    dfg_new = read_write_collapse(analysis, dfg_old)
    if verbose:
        n_pre_quads = sum(isinstance(node, Quads) for node in dfg_old.nodes())
        n_post_quads = sum(isinstance(node, Quads) for node in dfg_new.nodes())
        print(
            f"Read/write collapsed {n_pre_quads} -> {n_post_quads} quads; {len(dfg_old.nodes())} -> {len(dfg_new.nodes())} nodes; {len(dfg_old.edges())} -> {len(dfg_new.edges())} edges"
        )
    dfg_old = dfg_new

    dfg_new = compress_twin_ivns(dfg_old)
    if verbose:
        n_pre_ivns = sum(isinstance(node, IVNs) for node in dfg_old.nodes())
        n_post_ivns = sum(isinstance(node, IVNs) for node in dfg_new.nodes())
        print(
            f"Combined twin inodes {n_pre_ivns} -> {n_post_ivns} IVNs; {len(dfg_old.nodes())} -> {len(dfg_new.nodes())} nodes; {len(dfg_old.edges())} -> {len(dfg_new.edges())} edges"
        )
    dfg_old = dfg_new

    dfg_new = collapse_thread_cycles(dfg_old)
    if verbose:
        n_pre_quads = sum(isinstance(node, Quads) for node in dfg_old.nodes())
        n_post_quads = sum(isinstance(node, Quads) for node in dfg_new.nodes())
        print(
            f"Collapsed cycles {n_pre_quads} -> {n_post_quads} quads; {len(dfg_old.nodes())} -> {len(dfg_new.nodes())} nodes; {len(dfg_old.edges())} -> {len(dfg_new.edges())} edges"
        )
    dfg_old = dfg_new

    return dfg_old


class PidState(enum.IntEnum):
    READING = enum.auto()
    WRITING = enum.auto()


def is_out_of_thread(thread_triple: ptypes.ThreadTriple, node: Quads | IVNs) -> bool:
    return isinstance(node, IVNs) or (any(quad.thread_triple() != thread_triple for quad in node))


def compressed_dfg_node_flattener(nodes: frozenset[Quads | IVNs]) -> Quads | IVNs:
    if all(isinstance(node, Quads) for node in nodes):
        quadss = typing.cast(It[Quads], nodes)
        exec_pairs = frozenset(quad.exec_pair() for quads in quadss for quad in quads)
        assert len(exec_pairs) == 1, exec_pairs
        return Quads(frozenset({quad for quads in quadss for quad in quads}))
    elif all(isinstance(node, IVNs) for node in nodes):
        ivnss = typing.cast(It[IVNs], nodes)
        return IVNs(ivn for ivns in ivnss for ivn in ivns)
    else:
        raise TypeError(nodes)


@charmonium.time_block.decor(print_start=False)
def compress_twin_ivns(dfg_in: DataflowGraph) -> DataflowGraph:
    return graph_utils.map_nodes(
        compressed_dfg_node_flattener,
        graph_utils.combine_twin_nodes(
            dfg_in,
            lambda node: isinstance(node, IVNs),
        ),
    )


@charmonium.time_block.decor(print_start=False)
def read_write_collapse(
    analysis: Analysis,
    dfg_in: DataflowGraph,
) -> DataflowGraph:
    "Collapse N reads + M writes into 1 node with FSA"
    triples_to_nodes = dict[ptypes.ThreadTriple, list[tuple[int, Quads]]]()
    for node in dfg_in.nodes():
        if isinstance(node, Quads):
            try:
                thread_triple = node.thread_triple()
                earliest_op_no = min(quad.op_no for quad in node)
                triples_to_nodes.setdefault(thread_triple, []).append((earliest_op_no, node))
            except ValueError as exc:
                raise ValueError(
                    f"This algorithm assumes all nodes represent quads from just one thread, got: {node.thread_triples()} {str(exc)}"
                )
    all_runs = list[list[Quads]]()
    for thread_triple, nodes in tqdm.tqdm(
        list(triples_to_nodes.items()), desc="Read/write collapse thread-triples"
    ):
        state = PidState.READING
        nodes = sorted(nodes, key=lambda pair: pair[0])
        this_run = list[Quads]()
        for _, node in nodes:
            out_of_thread_preds = [
                pred for pred in dfg_in.predecessors(node) if is_out_of_thread(thread_triple, pred)
            ]
            out_of_thread_succs = [
                succ for succ in dfg_in.successors(node) if is_out_of_thread(thread_triple, succ)
            ]
            match state:
                case PidState.READING:
                    # Always add preds when in read mode
                    this_run.append(node)
                    if out_of_thread_succs:
                        # read-and-write is also acceptable, but we have to switch modes
                        state = PidState.WRITING
                case PidState.WRITING:
                    if out_of_thread_preds:
                        all_runs.append(this_run)

                        # Set up the new run
                        state = PidState.READING
                        this_run = [node]

                        # read-and-write is also acceptable, but we have to switch modes
                        if out_of_thread_succs:
                            state = PidState.WRITING
                    else:
                        # If no reads, we can append succs
                        this_run.append(node)
        if this_run:
            all_runs.append(this_run)
    node_mapper: Map[Quads | IVNs, Quads | IVNs] = {
        node: Quads(quad for node in run for quad in node) for run in all_runs for node in run
    }
    with charmonium.time_block.ctx("map nodes"):
        ret = graph_utils.map_nodes(
            lambda node: node_mapper.get(node, node),
            dfg_in,
            check_unique=False,
        )
    return ret


@charmonium.time_block.decor(print_start=False)
def collapse_thread_cycles(dfg_in: DataflowGraph) -> DataflowGraph:
    "Collapse cycles that are within one execpair"
    # with charmonium.time_block.ctx("simple_cycles", print_start=False):
    #     dfg2 = typing.cast(
    #         "networkx.DiGraph[Quads]",
    #         dfg_in.subgraph([node for node in dfg_in.nodes() if isinstance(node, Quads)]),
    #     )
    #     cycles = list(networkx.strongly_connected_components(dfg2))
    # mapper = dict[Quads | IVNs, Quads | IVNs]()
    # for scc in tqdm.tqdm(cycles, desc="sccs"):
    #     scc_nodes_by_exec_pair = util.groupby_dict(
    #         scc,
    #         key_func=lambda node: node.exec_pair(),
    #         value_func=lambda node: node,
    #     )
    #     for nodes_same_exec_pair in scc_nodes_by_exec_pair.values():
    #         sum_node = Quads(set().union(*[
    #             quads
    #             for quads in nodes_same_exec_pair
    #         ]))
    #         for node in nodes_same_exec_pair:
    #             mapper[node] = sum_node
    # ret = networkx.relabel_nodes(dfg_in, mapper)
    # graph_utils.remove_self_edges(ret)
    # return ret
    return dfg_in


def trivial_compress(
    dfg_in: UncompressedDataflowGraph,
) -> DataflowGraph:
    def node_mapper(node: ptypes.OpQuad | InodeVersionNode) -> Quads | IVNs:
        if isinstance(node, ptypes.OpQuad):
            return Quads(frozenset({node}))
        elif isinstance(node, InodeVersionNode):
            return IVNs({node})
        else:
            raise TypeError(node)

    return graph_utils.map_nodes(node_mapper, dfg_in, False)


def label_nodes(
    analysis: Analysis,
    dfg: DataflowGraph,
    relative_to: pathlib.Path,
    max_args: int = 5,
    max_arg_length: int = 200,
    max_path_length: int = 200,
    max_path_segment_length: int = 80,
    max_paths_per_inode: int = 10,
    max_inodes_per_set: int = 100,
    ignore_paths: It[str] = (),
    include_paths: It[str] = (),
) -> None:
    for node in tqdm.tqdm(sorted(dfg.nodes(), key=node_sort_key), desc="label dfg"):
        data2 = dfg.nodes(data=True)[node]
        match node:
            case Quads():
                label_quads(
                    node,
                    data2,
                    analysis,
                    max_args=max_args,
                    max_arg_length=max_arg_length,
                )
            case IVNs():
                label_ivns(
                    node,
                    data2,
                    analysis,
                    relative_to,
                    max_path_length=max_path_length,
                    max_path_segment_length=max_path_segment_length,
                    max_paths_per_inode=max_paths_per_inode,
                    max_inodes_per_set=max_inodes_per_set,
                    ignore_paths=ignore_paths,
                    include_paths=include_paths,
                )
            case _:
                raise TypeError()
    for node0, node1, edge_data in dfg.edges(data=True):
        if "label" in edge_data:
            del edge_data["label"]


def label_quads(
    quads: Quads,
    data: NodeData,
    analysis: Analysis,
    max_args: int,
    max_arg_length: int,
) -> None:
    thread_triple = list(quads)[0].thread_triple()
    min_op_no = min(quad.op_no for quad in quads)
    max_op_no = max(quad.op_no for quad in quads)
    data["id"] = (
        f"pid_{thread_triple.pid}_exec_{thread_triple.exec_no}_thread_{thread_triple.tid}_ops_{min_op_no}_to_{max_op_no}"
    )
    data["label"] = ""
    data["cluster"] = f"Process {thread_triple.pid}"
    data["shape"] = "oval"
    for quad in quads:
        try:
            op_data = analysis.probe_log.get_op(quad).data
        except KeyError:
            data["label"] += "Unknown"
        else:
            if isinstance(op_data, headers.InitExecEpoch):
                if quad.exec_no == 0:
                    if quad.pid == analysis.probe_log.get_root_pid():
                        data["label"] += "(root process)"
                    else:
                        data["label"] += "(child process)"
                else:
                    args = [
                        arg.decode(errors="backslashreplace") for arg in op_data.argv[0:max_args]
                    ]
                    args = [
                        arg if len(arg) < max_arg_length else arg[:max_arg_length] + "…"
                        for arg in args
                    ]
                    if len(args) > max_args:
                        args_str = shlex.join(args[:max_args]) + ", …"
                    else:
                        args_str = shlex.join(args)
                    data["label"] += args_str
    if thread_triple.tid != thread_triple.pid.main_thread():
        data["label"] += f"Thread {int(quad.tid) - int(quad.pid)}"


def label_ivns(
    ivns: IVNs,
    data: NodeData,
    analysis: Analysis,
    relative_to: pathlib.Path,
    max_path_length: int,
    max_path_segment_length: int,
    max_paths_per_inode: int,
    max_inodes_per_set: int,
    ignore_paths: It[str],
    include_paths: It[str],
) -> None:
    inode_labels = []
    # Sorting ensures consistent labels
    ivns_sorted = sorted(ivns)
    for inode_version in ivns_sorted[:max_inodes_per_set]:
        type = inode_version.inode.type
        if type == "-":
            type_str = ""
        else:
            type_str = f" (type={type})"
        paths = analysis.paths.get(inode_version.inode, collections.Counter[pathlib.Path]())
        for path, frequency in list(paths.most_common()):
            if not any(
                fnmatch.fnmatch(str(path), ignore_path) for ignore_path in ignore_paths
            ) or any(fnmatch.fnmatch(str(path), include_path) for include_path in include_paths):
                path_str = shorten_path(path, max_path_length, max_path_segment_length, relative_to)
                inode_labels.append(f"{path_str}{type_str}")
        if not paths:
            inode_labels.append(
                f"<unk {inode_version.inode.number}>{type_str} ver={inode_version.version}"
            )
            if len(inode_labels) > max_paths_per_inode:
                break
    if len(ivns) > max_inodes_per_set:
        inode_labels.append("…")
    if not inode_labels:
        inode_labels.append("<system files>")
    data["label"] = "\n".join(inode_labels)
    data["shape"] = "rectangle"
    number = ivns_sorted[0].inode.number
    version = ivns_sorted[0].version
    data["id"] = f"inodes_{number}_v_{version}"


def shorten_path(
    input: pathlib.Path,
    max_path_length: int,
    max_path_segment_length: int,
    relative_to: pathlib.Path,
) -> str:
    if relative_to != pathlib.Path("/") and input.is_absolute() and relative_to.is_absolute():
        input2 = input.relative_to(relative_to, walk_up=True)
        if sum(part == ".." for part in input2.parts) > 2:
            input2 = input
    else:
        input2 = input
    output = ("/" if input2.is_absolute() else "") + "/".join(
        textwrap.shorten(segment, width=max_path_segment_length)
        for segment in input2.parts
        if segment != "/"
    )
    if len(output) > max_path_length:
        output = "…" + output[-max_path_length:]
    return output


def node_sort_key(node: Quads | IVNs | ptypes.OpQuad | InodeVersionNode) -> typing.Any:
    """Node sorting gives us deterministic labels. Works on compressed or uncompressed graphs."""
    if isinstance(node, ptypes.OpQuad):
        return (1, node)
    elif isinstance(node, InodeVersionNode):
        return (0, node)
    elif isinstance(node, Quads):
        min_quad = min(node)
        return (1, min_quad)
    elif isinstance(node, IVNs):
        min_ivn = min(node)
        return (0, min_ivn)
    else:
        raise TypeError(node)


def format_interval(interval: partial_order.Interval[ptypes.OpQuad]) -> str:
    upper_bound = ", ".join(
        f"{quad.pid}.{quad.exec_no}.{quad.tid}.{quad.op_no}" for quad in interval.upper_bound
    )
    lower_bound = ", ".join(
        f"{quad.pid}.{quad.exec_no}.{quad.tid}.{quad.op_no}" for quad in interval.lower_bound
    )
    return f"[{upper_bound}]--[{lower_bound}]"
