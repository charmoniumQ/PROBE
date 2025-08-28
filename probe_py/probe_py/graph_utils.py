from __future__ import annotations
import abc
import collections
import dataclasses
import functools
import itertools
import typing
import pathlib
import random
import charmonium.time_block
import networkx
import pydot
from . import util


_Node = typing.TypeVar("_Node")


@dataclasses.dataclass(frozen=True)
class Segment(typing.Generic[_Node]):
    dag_tc: ReachabilityOracle[_Node]
    upper_bound: frozenset[_Node]
    lower_bound: frozenset[_Node]

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

    @staticmethod
    def singleton(dag_tc: ReachabilityOracle[_Node], node: _Node) -> Segment[_Node]:
        return Segment(dag_tc, frozenset({node}), frozenset({node}))

    def __bool__(self) -> bool:
        "Whether the segment is non-empty"
        return bool(self.upper_bound)

    @staticmethod
    def union(*segments: Segment[_Node]) -> Segment[_Node]:
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

    def all_greater_than(self, other: Segment[_Node]) -> bool:
        other_upper_bounds_that_are_not_descendent_of_self_lower_bounds = \
            self.dag_tc.non_descendants(other.upper_bound, self.lower_bound)
        return not other_upper_bounds_that_are_not_descendent_of_self_lower_bounds


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
    dct = {node: function(node) for node in graph.nodes()}
    assert util.all_unique(dct.values()), util.duplicates(dct.values())
    ret = typing.cast("networkx.DiGraph[_Node2]", networkx.relabel_nodes(graph, dct))
    return ret


def serialize_graph(
        graph: networkx.DiGraph[_Node],
        output: pathlib.Path,
        name_mapper: typing.Callable[[_Node], str] | None = None,
        cluster_labels: collections.abc.Mapping[str, str] = {},
) -> None:
    if name_mapper is None:
        name_mapper = typing.cast(
            typing.Callable[[_Node], str],
            lambda node: graph.nodes(data=True)[node].get("id", str(node)),
        )
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


def search_with_pruning(
        digraph: networkx.DiGraph[_Node],
        start: _Node,
        breadth_first: bool = True,
        sort_nodes: typing.Callable[[list[_Node]], list[_Node]] = lambda lst: lst,
) -> typing.Generator[_Node | None, bool | None, None]:
    """DFS/BFS but send False to prune this branch

        traversal = bfs_with_pruning
        for node in traversal:
            # work on node
            traversal.send(condition) # send True to descend or False to prune

    """
    queue = collections.deque([start])
    while queue:
        node = queue.pop()
        # When we yield, we do the body of the client's for-loop with "node"
        # Until they do bfs.send(...)
        # At which point we resume
        continue_with_children = yield node
        # Now we resumed.
        # When we yield this time, the caller's bfs.send(...) returns "None"
        should_be_none = yield None
        # Now the for-loop has wrapped around and we are back here.
        assert should_be_none is None
        if continue_with_children:
            children = sort_nodes(list(digraph.successors(node)))
            if breadth_first:
                queue.extend(children)
            else:
                queue.extendleft(children[::-1])


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
            upper_bounds: collections.abc.Iterable[_Node],
            lower_bounds: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        ...

    @abc.abstractmethod
    def add_edge(self, u: _Node, v: _Node) -> None:
        """Keep datastructure up-to-date"""

    def dominates(self, source: _Node, destination: _Node) -> bool:
        return self.n_paths(source, destination) == 1

    @abc.abstractmethod
    def n_paths(self, source: _Node, destination: _Node) -> int: ...

    def is_antichain(self, nodes: collections.abc.Iterable[_Node]) -> bool:
        return all(
            not self.is_reachable(node0, node1)
            for node0, node1 in itertools.combinations(nodes, 2)
        )

    def sorted(self, nodes: collections.abc.Iterable[_Node]) -> collections.abc.Sequence[_Node]:
        dag: networkx.DiGraph[_Node] = networkx.DiGraph()
        dag.add_nodes_from(nodes)
        dag.add_edges_from([
            (source, target)
            for source in nodes
            for target in nodes
            if self.is_reachable(source, target)
            and source != target
        ])
        return list(networkx.topological_sort(dag))

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
        assert all(
            any(
                uppermost_node == node or self.is_reachable(uppermost_node, node)
                for uppermost_node in uppermost_nodes)
            for node in nodes
        )
        assert not any(
            self.is_reachable(a, b)
            for a in uppermost_nodes
            for b in uppermost_nodes
            if a != b
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
        assert all(
            any(
                bottom_node == node or self.is_reachable(node, bottom_node)
                for bottom_node in bottom_nodes
            )
            for node in nodes
        )
        assert not any(
            self.is_reachable(a, b)
            for a in bottom_nodes
            for b in bottom_nodes
            if a != b
        )
        return frozenset(bottom_nodes)

    def non_ancestors(
            self,
            candidates: collections.abc.Iterable[_Node],
            lower_bounds: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        "Return all candidates that are not ancestors of any element in lower_bounds."
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
        "Return all candidates that are not descendent of any element in upper_bounds."
        return frozenset({
            candidate
            for candidate in candidates
            if not any(
                    self.is_reachable(upper_bound, candidate)
                    for upper_bound in upper_bounds
            )
        })

    def segment(self, upper_bound: frozenset[_Node], lower_bound: frozenset[_Node]) -> Segment[_Node]:
        return Segment(self, upper_bound, lower_bound)


@dataclasses.dataclass(frozen=True)
class PrecomputedReachabilityOracle(ReachabilityOracle[_Node]):
    dag: networkx.DiGraph[_Node]
    dag_tc: networkx.DiGraph[_Node]

    @staticmethod
    def create(dag: networkx.DiGraph[_Node]) -> PrecomputedReachabilityOracle[_Node]:
        return PrecomputedReachabilityOracle(
            dag,
            dag_transitive_closure(dag),
        )

    def is_reachable(self, u: _Node, v: _Node) -> bool:
        return v in self.dag_tc.successors(u) or u == v

    def nodes_between(
            self,
            upper_bounds: collections.abc.Iterable[_Node],
            lower_bounds: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        raise NotImplementedError()

    def add_edge(self, source: _Node, target: _Node) -> None:
        if target not in self.dag_tc.successors(source):
            for descendant_of_source in [*self.dag_tc.successors(source), source]:
                for descendant_of_target in [*self.dag_tc.successors(target), target]:
                    self.dag_tc.add_edge(descendant_of_source, descendant_of_target)

    @functools.cache
    def n_paths(self, source: _Node, destination: _Node) -> int:
        if self.dag.in_degree(destination) == 1:
            return int(self.is_reachable(source, destination))
        else:
            return sum(
                1 if predecessor == source else self.n_paths(source, predecessor)
                for predecessor in self.dag.predecessors(destination)
            )


def get_faces(
        planar_graph: networkx.PlanarEmbedding[_Node],
) -> frozenset[tuple[_Node, ...]]:
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


def add_edge_without_cycle(
        dag: networkx.DiGraph[_Node],
        source: _Node,
        target: _Node,
        reachability_oracle: ReachabilityOracle[_Node] | None = None,
) -> collections.abc.Sequence[tuple[_Node, _Node]]:
    """
    Add an edge from source to the earliest descendants of target without creating a cycle.

    Consider the graph:

    0 -> 10, 20, 30;
    10 -> 11;
    20 -> 21;
    30 -> 31;

    If we add the edge 31 -> 0, that would create a cycle.
    So we look at the children of 0.
    We add the edge 31 -> 10.
    We add the edge 31 -> 20.
    We don't add 31 -> 30, because that would create a cycle.
    We recurse into 31's aunts and uncles, add edges to them, etc.
    """

    if reachability_oracle is None:
        assert networkx.is_directed_acyclic_graph(dag)
        reachability_oracle = PrecomputedReachabilityOracle.create(dag)

    if reachability_oracle.is_reachable(source, target):
        # No cycle would be made anyway.
        # Easy.
        return [(source, target)]
    else:
        edges = []
        # Start from target
        # See if each descendant can be used as a proxy for target.
        # I.e., source -> proxy_target.
        # If not, we will have to recurse into its children until a suitable target is found or the original source is found.
        bfs = search_with_pruning(dag, target, breadth_first=True)
        for proxy_target in bfs:
            assert proxy_target is not None
            if reachability_oracle.is_reachable(proxy_target, source):
                # Upstream of source
                # An edge here would create a cycle.
                # We will recurse into the children to find a suitable proxy target.
                bfs.send(True)
            elif reachability_oracle.is_reachable(source, proxy_target) or proxy_target == source:
                # Downstream of target (or equal to target).
                # Time to stop.
                bfs.send(False)
            else:
                # Neither upstpream nor downstream.
                # We can put an edge here and quit.
                edges.append((source, proxy_target))
                bfs.send(False)
        # checking:
        dag2 = dag.copy()
        dag2.add_edges_from(edges)
        assert networkx.is_directed_acyclic_graph(dag2)
        return edges


@charmonium.time_block.decor(print_start=False)
def splice_out_nodes(
        input_dag: networkx.DiGraph[_Node],
        should_splice: typing.Callable[[_Node], bool],
) -> networkx.DiGraph[_Node]:
    output_dag = input_dag.copy()
    for node in list(input_dag.nodes()):
        if should_splice(node):
            output_dag.add_edges_from([
                (predecessor, successor)
                for predecessor in output_dag.predecessors(node)
                for successor in output_dag.predecessors(node)
                if predecessor != node and successor != node
            ])
            output_dag.remove_node(node)
    return output_dag


def topological_sort_depth_first(
        dag: networkx.DiGraph[_Node],
        starting_node: _Node | None = None,
        score_children: typing.Callable[[_Node, _Node], int] = lambda _parent, _child: 0,
        reachability_oracle: ReachabilityOracle[_Node] | None = None
) -> typing.Generator[_Node | None, bool | None, None]:
    """Topological sort that breaks ties by depth first, and then by lowest child score.

    If `starting_node` is given, iterate only over nodes reachable from
    starting_node. We don't load up all nodes in the graph ahead-of-time; we
    start exploring from starting_node. We need a reachability oracle to
    determine when all the paths from starting_node to node have been hit (there
    could be paths ending in node that don't go through starting node).

    See `search_with_pruning` for example of how to iterate and prune.

    """

    degree_func2: typing.Callable[[_Node], int]
    if starting_node is None:
        degree_func2 = dag.in_degree
    else:
        assert reachability_oracle is not None
        degree_func2 = lambda node: sum(
            reachability_oracle.is_reachable(starting_node, predecessor)
            for predecessor in dag.predecessors(node)
        )

    queue = util.PriorityQueue[_Node, tuple[int, int]]()

    if starting_node is not None:
        queue[starting_node] = (0, -1)
        assert queue.peek() == ((0, -1), starting_node)
    else:
        for node in dag.nodes():
            queue[node] = (degree_func2(node), 0)
        # Because queue is sorted,
        # Iteration will start from one of the zero-degree ndoes

    counter = 0
    # seen = set()
    while queue:
        (in_degree, tie_breaker), node = queue.pop()
        if in_degree != 0:
            break

        # if starting_node is None:
        #     assert all(predecessor in seen for predecessor in dag.predecessors(node))
        # else:
        #     assert reachability_oracle
        #     assert all(predecessor in seen for predecessor in dag.predecessors(node) if reachability_oracle.is_reachable(starting_node, predecessor))
        # seen.add(node)

        continue_with_children = yield node
        should_be_none = yield None
        assert should_be_none is None

        # Since we handled the parent, we essentially removed it from the graph
        # decrementing the in-degree of its children by one.
        # To make it be depth first, we make it "win" all ties, among currently existing entries.
        if continue_with_children:
            for child in sorted(dag.successors(node), key=lambda child: score_children(node, child)):
                if child in queue:
                    in_degree, tie_breaker = queue[child]
                    queue[child] = (in_degree - 1, -counter)
                else:
                    queue[child] = (degree_func2(child) - 1, -counter)
        counter += 1


@charmonium.time_block.decor(print_start=False)
def dag_transitive_closure(dag: networkx.DiGraph[_Node]) -> networkx.DiGraph[_Node]:
    tc: networkx.DiGraph[_Node] = networkx.DiGraph()
    node_order = list(networkx.topological_sort(dag))[::-1]
    for src in node_order:
        tc.add_node(src)
        for child in dag.successors(src):
            tc.add_edge(src, child)
            for grandchild in tc.successors(child):
                tc.add_edge(src, grandchild)
    return tc


def combine_isomorphic_nodes(
    graph: networkx.DiGraph[_Node],
    combinable: typing.Callable[[_Node], bool],
) -> networkx.DiGraph[frozenset[_Node] | _Node]:
    neighbors_to_node = dict[tuple[frozenset[_Node], frozenset[_Node]], set[_Node]]()
    non_combinable_nodes = set()
    for node in graph.nodes():
        if combinable(node):
            preds = frozenset(graph.predecessors(node))
            succs = frozenset(graph.successors(node))
            neighbors_to_node.setdefault((preds, succs), set()).add(node)
        else:
            non_combinable_nodes.add(node)
    node_to_equivalence_class: collections.abc.Mapping[_Node, frozenset[_Node] | _Node] = {
        **{
            node: frozenset(equivalence_class)
            for equivalence_class in neighbors_to_node.values()
            for node in equivalence_class
        },
        **{
            node: node
            for node in non_combinable_nodes
        },
    }
    ret: networkx.DiGraph[frozenset[_Node] | _Node] = networkx.DiGraph()
    ret.add_nodes_from(
        frozenset(equivalence_class)
        for equivalence_class in neighbors_to_node.values()
    )
    ret.add_nodes_from(non_combinable_nodes)
    ret.add_edges_from(
        (frozenset(equivalence_class), node_to_equivalence_class[successor])
        for (_, successors), equivalence_class in neighbors_to_node.items()
        for successor in successors
    )
    ret.add_edges_from(
        (node, node_to_equivalence_class[successor])
        for node in non_combinable_nodes
        for successor in graph.successors(node)
    )
    return ret


class GraphvizAttributes(typing.TypedDict):
    label: str
    labelfontsize: int
    color: str
    shape: str


class GraphvizNodeAttributes(typing.TypedDict):
    label: str
    labelfontsize: int
    color: str
    style: str
    cluster: str


class GraphvizEdgeAttributes(typing.TypedDict):
    label: str
    shape: str
    color: str
    style: str
    labelfontsize: int
