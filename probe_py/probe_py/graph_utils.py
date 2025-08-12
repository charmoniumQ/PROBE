from __future__ import annotations
import abc
import collections.abc
import tqdm
import dataclasses
import itertools
import typing
import pathlib
import random
import networkx
import pydot
from . import util


_Node = typing.TypeVar("_Node")


_CoNode = typing.TypeVar("_CoNode", covariant=True)


@dataclasses.dataclass(frozen=True)
class Segment(typing.Generic[_CoNode]):
    dag_tc: ReachabilityOracle[_CoNode]
    upper_bound: frozenset[_CoNode]
    lower_bound: frozenset[_CoNode]

    def __post_init__(self) -> None:
        assert self.upper_bound
        assert self.lower_bound
        assert self.dag_tc.is_antichain(self.upper_bound), \
            f"{self.upper_bound} is not an antichain"
        assert self.dag_tc.is_antichain(self.lower_bound), \
            f"{self.lower_bound} is not an antichain"
        unbounded = self.dag_tc.non_ancestors(self.upper_bound, self.lower_bound)
        assert not unbounded, \
            f"{unbounded} in self.upper_bound is not an ancestor of any any in {self.lower_bound=}"
        unbounded = self.dag_tc.non_descendants(self.lower_bound, self.upper_bound)
        assert not unbounded, \
            f"{unbounded} in self.lower_bound is not a descendant of any in {self.upper_bound=}"

    def nodes(self) -> collections.abc.Iterable[_CoNode]:
        return self.dag_tc.nodes_between(self.upper_bound, self.lower_bound)

    def overlaps(self, other: Segment[_CoNode]) -> bool:
        assert self.dag_tc is other.dag_tc
        return bool(frozenset(self.nodes()) & frozenset(other.nodes()))

    @staticmethod
    def union(segments: typing.Sequence[Segment[_CoNode]]) -> Segment[_CoNode]:
        assert segments
        dag_tc = segments[0].dag_tc
        assert all(segment.dag_tc is dag_tc for segment in segments)
        upper_bound = dag_tc.get_uppermost(frozenset(
            node
            for segment in segments
            for node in segment.upper_bound
        ))
        lower_bound = dag_tc.get_bottommost(frozenset(
            node
            for segment in segments
            for node in segment.lower_bound
        ))
        return Segment(dag_tc, frozenset(upper_bound), frozenset(lower_bound))


_Node2 = typing.TypeVar("_Node2")


def hasse_diagram(
        elements: typing.Iterable[_Node],
        leq: typing.Callable[[_Node, _Node], bool],
) -> networkx.DiGraph[_Node]:
    dag: networkx.DiGraph[_Node] = networkx.DiGraph()
    dag.add_nodes_from(elements)
    for e0, e1 in itertools.permutations(elements, 2):
        if leq(e0, e1):
            dag.add_edge(e0, e1)
    assert networkx.is_directed_acyclic_graph(dag)
    return dag


def map_nodes(
        function: typing.Callable[[_Node], _Node2],
        graph: networkx.DiGraph[_Node],
        check: bool = True,
) -> networkx.DiGraph[_Node2]:
    dct = {node: function(node) for node in tqdm.tqdm(graph.nodes(), desc="nodes")}
    assert util.all_unique(dct.values()), util.duplicates(dct.values())
    return networkx.relabel_nodes(graph, dct)


def serialize_graph(
        graph: networkx.DiGraph[_Node],
        output: pathlib.Path,
        name_mapper: typing.Callable[[_Node], str] | None = None,
        cluster_labels: collections.abc.Mapping[str, str] = {},
) -> None:
    if name_mapper is None:
        nodes_data = graph.nodes(data=True)
        name_mapper = typing.cast(typing.Callable[[_Node], str], lambda node: nodes_data[node].get("id", str(node)))
    graph2 = map_nodes(name_mapper, graph)
    pydot_graph = networkx.drawing.nx_pydot.to_pydot(graph2)

    pydot_graph.set("rankdir", "TB")

    clusters = dict[str, pydot.Subgraph]()
    for node in pydot_graph.get_nodes():
        cluster_name = node.get("cluster")
        if cluster_name:
            if cluster_name not in clusters:
                cluster_subgraph = pydot.Subgraph(
                    f"cluster_{cluster_name}",
                    label=cluster_labels.get(cluster_name, cluster_name),
                )
                pydot_graph.add_subgraph(cluster_subgraph)
            else:
                cluster_subgraph = clusters[cluster_name]
            cluster_subgraph.add_node(node)

    pydot_graph.write(str(output), "raw")


def add_self_loops(
        digraph: networkx.DiGraph[_Node],
        copy: bool,
) -> networkx.DiGraph[_Node]:
    if copy:
        digraph = digraph.copy()
    for node in digraph.nodes():
        digraph.add_edge(node, node)
    return digraph


def replace(digraph: networkx.DiGraph[_Node], old: _Node, new: _Node) -> None:
    for pred in list(digraph.predecessors(old)):
        if pred != old:
            digraph.remove_edge(pred, old)
            digraph.add_edge(pred, new)

    for succ in list(digraph.successors(old)):
        if succ != old:
            digraph.remove_edge(old, succ)
            digraph.add_edge(new, succ)

    if digraph.has_edge(old, old):
        digraph.add_edge(new, new)

    digraph.remove_node(old)


def bfs_with_pruning(
        digraph: networkx.DiGraph[_Node],
        start: _Node,
        left_to_right: bool = False
) -> typing.Generator[_Node, bool, None]:
    """BFS but send False to prune this branch"""
    queue = [start]
    while queue:
        node = queue.pop()
        continue_with_children = yield node
        if continue_with_children:
            children = list(digraph.successors(node))
            if left_to_right:
                children = children[::-1]
            queue.extend(children)


def get_sources(dag: networkx.DiGraph[_Node]) -> list[_Node]:
    return [
        node
        for node in dag.nodes()
        if dag.in_degree(node) == 0
    ]


def get_sinks(dag: networkx.DiGraph[_Node]) -> list[_Node]:
    return [
        node
        for node in dag.nodes()
        if dag.out_degree(node) == 0
    ]


def randomly_sample_edges(inp: networkx.DiGraph[_Node], factor: float, seed: int = 0) -> networkx.DiGraph[_Node]:
    out: networkx.DiGraph[_Node] = networkx.DiGraph()
    rng = random.Random(seed)
    inp_edges = list(inp.edges(data=True))
    for src, dst, data in rng.sample(inp_edges, round(len(inp_edges) * factor)):
        out.add_edge(src, dst, **data)
    return out


class ReachabilityOracle(abc.ABC, typing.Generic[_Node]):
    """
    This datastructure answers reachability queries, is A reachable from B in dag.

    If you had only 1 reachability query, it would be best to DFS the graph from B, looking for A.
    DFS might have to traverse the whole graph and touch every edge, O(V+E).
    In fact, when A is _not_ a descendant of B (but we don't know that yet), if B is high up, then DFS approaches its worst case.
    Let's say you have N queries, resulting in O(N(V+E)) to complete all queries.

    If N gets to be larger than V, you're better off pre-computing reachability ahead of time.
    Because DFS tells you "all of the Bs descendent from A", we need to do DFS for each node as a source, resulting in, O(V(V+E)).
    This is conveniently implemented as [`networkx.transitive_closure`][source code].

    [source code]: https://networkx.org/documentation/stable/_modules/networkx/algorithms/dag.html#transitive_closure

    However, if V is on the order of 10^4 (E must be at least V for a connected graph), then V^2 could be terribly slow.
    There are more efficient datastructures for answering N queries, often involving some kind of preprocessing.
    This class encapsulate the preprocessing datastructure, and offers a method to answer reachability.
    """

    @staticmethod
    @abc.abstractmethod
    def create(dag: networkx.DiGraph[_Node]) -> ReachabilityOracle[_Node]:
        ...

    @abc.abstractmethod
    def is_reachable(self, u: _Node, v: _Node) -> bool:
        pass

    @abc.abstractmethod
    def nodes_between(
            self,
            u: collections.abc.Iterable[_Node],
            v: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        ...

    def is_antichain(self, nodes: collections.abc.Iterable[_Node]) -> bool:
        return all(
            not self.is_reachable(node0, node1)
            for node0, node1 in itertools.combinations(nodes, 2)
        )

    def sorted(self, nodes: collections.abc.Iterable[_Node]) -> collections.abc.Sequence[_Node]:
        return list(networkx.topological_sort(networkx.DiGraph(
            (source, target)
            for source in nodes
            for target in nodes
            if self.is_reachable(source, target)
        )))

    def get_uppermost(self, nodes: collections.abc.Iterable[_Node]) -> frozenset[_Node]:
        uppermost_nodes = set[_Node]()
        covered_nodes = set[_Node]()
        sorted_nodes = self.sorted(nodes)
        for i, candidate in enumerate(sorted_nodes):
            if candidate not in covered_nodes:
                uppermost_nodes.add(candidate)
                covered_nodes.update(
                    descendant
                    for descendant in sorted_nodes[i+1:]
                    if self.is_reachable(candidate, descendant)
                )
        return frozenset(uppermost_nodes)

    def get_bottommost(self, nodes: collections.abc.Iterable[_Node]) -> frozenset[_Node]:
        bottom_nodes = set[_Node]()
        covered_nodes = set[_Node]()
        sorted_nodes = self.sorted(nodes)[::-1]
        for i, candidate in enumerate(sorted_nodes):
            if candidate not in covered_nodes:
                bottom_nodes.add(candidate)
                covered_nodes.update(
                    ancestor
                    for ancestor in sorted_nodes[i+1:]
                    if self.is_reachable(ancestor, candidate)
                )
        return frozenset(bottom_nodes)

    def non_ancestors(
            self,
            candidates: collections.abc.Iterable[_Node],
            lower_bounds: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        return frozenset({
            candidate
            for candidate in candidates
            if not any(
                    self.is_reachable(candidate, lower_bound)
                    for lower_bound in lower_bounds
            )
        })

    def non_descendants(
            self,
            candidates: collections.abc.Iterable[_Node],
            upper_bounds: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        return frozenset({
            candidate
            for candidate in candidates
            if not any(
                    self.is_reachable(upper_bound, candidate)
                    for upper_bound in upper_bounds
            )
        })


@dataclasses.dataclass(frozen=True)
class PrecomputedReachabilityOracle(ReachabilityOracle[_Node]):
    dag_tc: networkx.DiGraph[_Node]

    @staticmethod
    def create(dag: networkx.DiGraph[_Node]) -> PrecomputedReachabilityOracle[_Node]:
        return PrecomputedReachabilityOracle(networkx.transitive_closure(dag))

    def is_reachable(self, u: _Node, v: _Node) -> bool:
        return v in self.dag_tc.successors(u)

    def nodes_between(
            self,
            u: collections.abc.Iterable[_Node],
            v: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        raise NotImplementedError()


def get_faces(planar_graph: networkx.PlanarEmbedding[_Node]) -> frozenset[tuple[_Node, ...]]:
    faces = set()
    covered_half_edges = set()
    for half_edge in planar_graph.edges():
        if half_edge not in covered_half_edges:
            covered_half_edges.add(half_edge)
            face = planar_graph.traverse_face(*half_edge)
            faces.add(tuple(face))
            if len(face) > 1:
                for a, b in [*zip(face[:-1], face[1:]), (face[-1], face[0])]:
                    covered_half_edges.add((a, b))
    return frozenset(faces)


@dataclasses.dataclass(frozen=True)
class KamedaReachabilityOracle(ReachabilityOracle[_Node]):
    """
    This implementaiton uses Kameda's algorithm because it is the simplest and fastest.
    The algorithm is described in [Kameda 1975] and on [Wikipedia].

    [Kameda 1975]: https://doi.org/10.1016/0020-0190(75)90019-8
    [Wikipedia]: https://en.wikipedia.org/wiki/Reachability#Kameda's_Algorithm

    However, this only works on a struct subset of planar graphs.
    Should the happens-before graphs violate this, alternative approaches may be found in the following survey papers:
    - [He 2025](https://doi.org/10.1007/978-981-96-8295-9_4)
    - [Yu 2010](https://doi.org/10.1007/978-1-4419-6045-0_6)
    - [Zhang 2023](https://doi.org/10.1145/3555041.3589408)
    """

    left_label: typing.Mapping[_Node, int]
    right_label: typing.Mapping[_Node, int]

    @staticmethod
    def create(dag: networkx.DiGraph[_Node]) -> ReachabilityOracle[_Node]:
        if not networkx.is_directed_acyclic_graph(dag):
            raise ValueError("Graph must be a DAG")
        is_planar, planar_graph = networkx.check_planarity(dag)
        if not is_planar:
            raise ValueError("We use Kameda's algorithm, which only works for planar DFGs.")
        assert planar_graph
        sources = set(get_sources(dag))
        sinks = set(get_sinks(dag))
        faces = get_faces(planar_graph)
        main_faces = [
            face
            for face in faces
            if sources | sinks <= set(face)
        ]
        if not main_faces:
            raise ValueError(f"We use Kameda's algorithm, which only works for planar DFGs where the sources and sinks lie on the same face.\n{sources=}\n{sinks=}\n{faces=}")
        main_face = main_faces[0]
        main_face_labels = [
            node in sources
            for node in main_face
            if node in sources | sinks
        ]
        switches = 0
        for a, b in [*zip(main_face_labels[:-1], main_face_labels[1:]), (main_face_labels[-1], main_face_labels[0])]:
            if a != b:
                switches += 1
        if switches > 2:
            raise ValueError("The main face needs to be partitionable between sources and sinks.")

        dag_aug = typing.cast(networkx.DiGraph[_Node | str], dag.copy())

        # Augment graph: add new sources and sinks
        source = "__KA_S__"
        target = "__KA_T__"
        dag_aug.add_node(source)
        dag_aug.add_node(target)
        for orig_node in dag.nodes():
            if dag.in_degree(orig_node) == 0:
                dag_aug.add_edge(source, orig_node)
            if dag.out_degree(orig_node) == 0:
                dag_aug.add_edge(orig_node, target)

        i = len(dag_aug) - 1
        left_label = {}
        bfs = bfs_with_pruning(dag_aug, source, False)
        while bfs:
            try:
                node = typing.cast(_Node, next(bfs))
            except StopIteration:
                break
            bfs.send(True)
            left_label[node] = i
            i -= 1

        # Second DFS: adjacencies right-to-left
        i = len(dag_aug) - 1
        right_label = {}
        bfs = bfs_with_pruning(dag_aug, source, True)
        while bfs:
            try:
                node = typing.cast(_Node, next(bfs))
            except StopIteration:
                break
            bfs.send(True)
            right_label[node] = i
            i -= 1
        return KamedaReachabilityOracle(left_label, right_label)

    def is_reachable(self, u: _Node, v: _Node) -> bool:
        u_left, u_right = self.left_label[u], self.right_label[u]
        v_left, v_right = self.left_label[v], self.right_label[v]
        # Both U components are less than both V components and at least one is strictly less.
        return u_left <= v_left and u_right <= v_right and (u_left < v_left or u_right < v_right)

    def nodes_between(
            self,
            u: collections.abc.Iterable[_Node],
            v: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        raise NotImplementedError()


def add_edge_without_cycle(
        dag: networkx.DiGraph[_Node],
        source: _Node,
        target: _Node,
) -> None:
    """
    Add an edge from source to the earliest descendants of target without creating a cycle.

    Consider:
    0 -> 10, 20, 30;
    10 -> 11;
    20 -> 21;
    30 -> 31;
    If we add the edge 31 -> 0, that would create a cycle.
    So we look at the children of 0.
    We add the edge 31 -> 10.
    We add the edge 31 -> 20.
    31 -> 30 would create a cycle.
    We recurse into 31's aunts and uncles.
    Finding it doesn't have any, we quit.
    """
    assert networkx.is_directed_acyclic_graph(dag)
    reachability = PrecomputedReachabilityOracle.create(dag)
    if reachability.is_reachable(source, target):
        # No cycle would be made anyway.
        # Easy.
        dag.add_edge(source, target)
    else:
        # Start from target
        # See if each descendant can be used as a proxy for target.
        # I.e., source -> proxy_target.
        # If not, we will have to recurse into its children until a suitable target is found or the original source is found.
        bfs = bfs_with_pruning(dag, target)
        while bfs:
            # Consider creating an edge from source -> proxy_target instead of source -> target.
            try:
                proxy_target = next(bfs)
            except StopIteration:
                break
            if reachability.is_reachable(proxy_target, source):
                # Upstream of source
                # An edge here would create a cycle.
                # We will recurse into the children to find a suitable proxy target.
                bfs.send(True)
            elif reachability.is_reachable(source, proxy_target) or proxy_target == source:
                # Downstream of target (or equal to target).
                # Time to stop.
                bfs.send(False)
            else:
                # Neither upstream nor downstream.
                # We can put an edge here and quit.
                dag.add_edge(source, proxy_target)
                bfs.send(False)
