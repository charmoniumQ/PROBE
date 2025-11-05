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
import frozendict
import networkx
import pydot
import tqdm
from . import util


_Node = typing.TypeVar("_Node")
_T_co = typing.TypeVar("_T_co", covariant=True)
_V_co = typing.TypeVar("_V_co", covariant=True)
FrozenDict: typing.TypeAlias = frozendict.frozendict[_T_co, _V_co]
NodeData = typing.Mapping[str, typing.Any]
EdgeData = typing.Mapping[str, typing.Any]
It: typing.TypeAlias = collections.abc.Iterable[_T_co]


@dataclasses.dataclass(frozen=True)
class Interval(typing.Generic[_Node]):
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
    def singleton(dag_tc: ReachabilityOracle[_Node], node: _Node) -> Interval[_Node]:
        return Interval(dag_tc, frozenset({node}), frozenset({node}))

    def __bool__(self) -> bool:
        "Whether the interval is non-empty"
        return bool(self.upper_bound)

    @staticmethod
    def union(*intervals: Interval[_Node]) -> Interval[_Node]:
        assert intervals
        dag_tc = intervals[0].dag_tc
        assert all(interval.dag_tc is dag_tc for interval in intervals)
        upper_bound = dag_tc.get_uppermost(frozenset(
            node
            for interval in intervals
            for node in interval.upper_bound
        ))
        lower_bound = dag_tc.get_bottommost(frozenset(
            node
            for interval in intervals
            for node in interval.lower_bound
        ))
        return Interval(dag_tc, frozenset(upper_bound), frozenset(lower_bound))

    def all_greater_than(self, other: Interval[_Node]) -> bool:
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
        mapper: typing.Callable[[_Node], _Node2],
        graph: networkx.DiGraph[_Node],
        check: bool = True,
) -> networkx.DiGraph[_Node2]:
    dct = {node: mapper(node) for node in tqdm.tqdm(graph.nodes(), desc="map nodes", total=len(graph.nodes()))}
    assert util.all_unique(dct.values()), util.duplicates(dct.values())
    ret = typing.cast("networkx.DiGraph[_Node2]", networkx.relabel_nodes(graph, dct))
    return ret


def filter_nodes(
        predicate: typing.Callable[[_Node], bool],
        graph: networkx.DiGraph[_Node],
) -> networkx.DiGraph[_Node]:
    kept_nodes = {
        node
        for node in tqdm.tqdm(graph.nodes(), desc="filter nodes", total=len(graph.nodes()))
        if predicate(node)
    }
    return create_digraph(
        kept_nodes,
        [
            (src, dst)
            for src, dst in tqdm.tqdm(graph.edges(), desc="filter edges", total=len(graph.edges()))
            if src in kept_nodes and dst in kept_nodes
        ]
    )


def serialize_graph(
        graph: networkx.DiGraph[_Node],
        output: pathlib.Path,
        name_mapper: typing.Callable[[_Node], str] | None = None,
        cluster_labels: collections.abc.Mapping[str, str] = {},
) -> None:
    if name_mapper is None:
        def name_mapper(node: _Node) -> str:
            return str(graph.nodes(data=True)[node].get("id", node))
    graph2 = map_nodes(name_mapper, graph)

    if output.suffix.endswith("dot"):
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
    elif output.suffix.endswith("graphml"):
        networkx.write_graphml(graph2, output)
    else:
        raise ValueError("Unknown output type")


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

    See

    - Zhang et al. 2025 <https://arxiv.org/pdf/2311.03542>
    """

    @staticmethod
    @abc.abstractmethod
    def create(dag: networkx.DiGraph[_Node]) -> ReachabilityOracle[_Node]:
        ...

    @abc.abstractmethod
    def __contains__(self, node: _Node) -> bool:
        ...

    @abc.abstractmethod
    def is_reachable(self, u: _Node, v: _Node) -> bool:
        ...

    def is_peer(self, u: _Node, v: _Node) -> bool:
        return not self.is_reachable(u, v) and not self.is_reachable(v, u)

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

    def interval(self, upper_bound: frozenset[_Node], lower_bound: frozenset[_Node]) -> Interval[_Node]:
        return Interval(self, upper_bound, lower_bound)


@dataclasses.dataclass(frozen=True)
class DualLabelReachabilityOracle(ReachabilityOracle[_Node]):
    """Dual-labelling algorithm

    See https://doi.org/10.1109/ICDE.2006.53
    """

    # FIXME: I think this is wrong; does not respect non-tree edges.

    dag: networkx.DiGraph[_Node]
    left: FrozenDict[_Node, int]
    right: FrozenDict[_Node, int]
    preorder: FrozenDict[_Node, int]

    def __contains__(self, node: _Node) -> bool:
        assert (node in self.dag) == (node in self.left) == (node in self.right) == (node in self.preorder), (node in self.dag, node in self.left, node in self.right, node in self.preorder)
        return node in self.dag

    @charmonium.time_block.decor(print_start=False)
    @staticmethod
    def create(dag: networkx.DiGraph[_Node]) -> DualLabelReachabilityOracle[_Node]:
        topo = list(networkx.topological_sort(dag))
        # Assign preorder numbers in topological order
        preorder = FrozenDict[_Node, int]({node: index for index, node in enumerate(topo)})
        # Initialize interval labels
        left = {node: preorder[node] for node in dag}
        right = {node: preorder[node] for node in dag}

        # Process nodes in reverse topological order
        for u in topo[::-1]:
            for v in dag.successors(u):
                left[u] = min(left[u], left[v])
                right[u] = max(right[u], right[v])
        return DualLabelReachabilityOracle(
            dag,
            FrozenDict[_Node, int](left),
            FrozenDict[_Node, int](right),
            preorder,
        )

    def is_reachable(self, src: _Node, dst: _Node) -> bool:
        if src not in self:
            raise KeyError(src)
        if dst not in self:
            raise KeyError(dst)
        return self.left[src] <= self.left[dst] and self.right[dst] <= self.right[src]

    def add_edge(self, source: _Node, target: _Node) -> None:
        raise NotImplementedError

    def nodes_between(
            self,
            upper_bounds: collections.abc.Iterable[_Node],
            lower_bounds: collections.abc.Iterable[_Node],
    ) -> collections.abc.Iterable[_Node]:
        raise NotImplementedError()

    @functools.cache
    def n_paths(self, source: _Node, destination: _Node) -> int:
        if self.dag.in_degree(destination) == 1:
            return int(self.is_reachable(source, destination))
        else:
            return sum(
                1 if predecessor == source else self.n_paths(source, predecessor)
                for predecessor in self.dag.predecessors(destination)
            )


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

    def __contains__(self, node: _Node) -> bool:
        return node in self.dag_tc

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


class GraphvizEdgeAttributes(typing.TypedDict):
    label: str
    shape: str
    color: str
    style: str
    labelfontsize: int


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


def _n_paths(
        dag: networkx.DiGraph[_Node],
        reachability_oracle: ReachabilityOracle[_Node],
        source: _Node,
        destination: _Node,
) -> int:
    return sum(
            int(reachability_oracle.is_reachable(source, predecessor))
            for predecessor in dag.predecessors(destination)
        )


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
        degree_func2 = functools.partial(_n_paths, dag, reachability_oracle, starting_node)

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
    print(f"DAG transitive closure of {len(list(dag.nodes()))} nodes, {len(list(dag.edges()))} edges")
    tc: networkx.DiGraph[_Node] = networkx.DiGraph()
    node_order = list(networkx.topological_sort(dag))[::-1]
    for src in tqdm.tqdm(node_order, desc="TC nodes"):
        tc.add_node(src)
        for child in dag.successors(src):
            tc.add_edge(src, child)
            for grandchild in tc.successors(child):
                tc.add_edge(src, grandchild)
    return tc


def combine_twin_nodes(
    graph: networkx.DiGraph[_Node],
    combinable: typing.Callable[[_Node], bool],
) -> networkx.DiGraph[frozenset[_Node]]:
    """Condensation, replacing combinable twins with a single node.

    - All nodes satisfying the combinable predicate will be replaced with a
      `frozenset[_Node]`. All "twin" nodes, that is nodes with the same
      in-neighbors and out-neighbors, will be combined into one frozenset.

    - Those not satisfying will remain a `_Node`, unchanged.

    Edges will be preserved according to the node mapping.

    """
    neighbors_to_node = dict[tuple[frozenset[_Node], frozenset[_Node]], list[_Node]]()
    non_combinable_nodes = set()
    for node in graph.nodes():
        if combinable(node):
            preds = frozenset(graph.predecessors(node))
            succs = frozenset(graph.successors(node))
            neighbors_to_node.setdefault((preds, succs), []).append(node)
        else:
            non_combinable_nodes.add(node)
    partitions = {
        *map(frozenset, neighbors_to_node.values()),
        *map(lambda node: frozenset({node}), non_combinable_nodes),
    }
    quotient = typing.cast(
        "networkx.DiGraph[frozenset[_Node]]",
        networkx.quotient_graph(graph, partitions),
    )
    for _, data in quotient.nodes(data=True):
        del data["nnodes"]
        del data["density"]
        del data["graph"]
        del data["nedges"]
    for _, _, data in quotient.edges(data=True):
        del data["weight"]
    return quotient


def retain_nodes_in_digraph(
        digraph: networkx.DiGraph[_Node],
        retained_nodes: frozenset[_Node],
) -> networkx.DiGraph[_Node]:
    """
    See retain_nodes_in_dag but for digraphs.
    """
    assert retained_nodes <= set(digraph.nodes())

    # Condensation is a DAG on the strongly-connected components (SCCs)
    # SCC is a set of nodes from which every is reachable to every other.
    condensation = networkx.condensation(digraph)

    # Retain only those SCCs containing a retained node, stitching the edges together appropriately.
    condensation = retain_nodes_in_dag(
        condensation,
        frozenset({
            scc
            for scc, data in condensation.nodes(data=True)
            if data["members"] & retained_nodes
        }),
        edge_data=lambda _digraph, _path: {},
    )

    # Convert each scc to a list of retained nodes in that scc.
    # All of the SCCs are disjoint, so this will be unique.
    # I use a tuple not a frozenset, because I will use the first and last to create a cycle later on.
    condensation2 = map_nodes(
        lambda node: tuple(sorted(condensation.nodes[node]["members"] & retained_nodes, key=hash)),
        condensation,
    )

    ret: networkx.DiGraph[_Node] = networkx.DiGraph()

    # Add nodes, keeping old edge data
    ret.add_nodes_from(
        (node, digraph.nodes[node])
        for node in retained_nodes
    )

    # Add edges between SCCs, using an arbitrary representative.
    ret.add_edges_from(
        (src_scc[0], dst_scc[0])
        for src_scc, dst_scc in condensation2.edges()
    )

    # Add edges within SCCs
    ret.add_edges_from(
        (src, dst)
        for scc in condensation2.nodes()
        if len(scc) > 1
        for src, dst in zip(scc[:-1], scc[1:])
    )

    # Need to connect last to first to complete the cycle within an SCC.
    ret.add_edges_from(
        (scc[-1], scc[0])
        for scc in condensation2.nodes()
        if len(scc) > 1
    )

    assert set(ret.nodes()) == retained_nodes

    return ret


def retain_nodes_in_dag(
        dag: networkx.DiGraph[_Node],
        retained_nodes: frozenset[_Node],
        edge_data: typing.Callable[[networkx.DiGraph[_Node], typing.Sequence[_Node]], EdgeData],
) -> networkx.DiGraph[_Node]:
    """Retruns a graph with only the retained nodes, such that:

    - if A and B are retained and connected by a path of non-retained nodes in the input,
      then there is an edge from A to B in the output, whose edge data is edge_data(dag, path_from_A_to_B).
    - and no other edges

    O(nodes + edges)
    """

    assert networkx.is_directed_acyclic_graph(dag)
    assert retained_nodes <= set(dag.nodes())

    # Node -> list of pairs of (path to latest retained predecessor, latest retained predecessor)
    # Note that there can be multiple "latest" due to partial ordering.
    # Note that could be itself (not truly a predecessor), but it simplifies the logic.
    latest_retained_predecessors: dict[_Node, typing.Sequence[tuple[typing.Sequence[_Node], _Node]]] = {}
    earliest_retained_successors: dict[_Node, typing.Sequence[tuple[typing.Sequence[_Node], _Node]]] = {}

    for node in networkx.topological_sort(dag):
        if node in retained_nodes:
            latest_retained_predecessors[node] = (((), node),)
        else:
            latest_retained_predecessors[node] = tuple(
                ((*path_to_retained_predecessor, node), retained_predecessor)
                for predecessor in dag.predecessors(node)
                for path_to_retained_predecessor, retained_predecessor in latest_retained_predecessors[predecessor]
            )

    for node in reversed(list(networkx.topological_sort(dag))):
        if node in retained_nodes:
            # path always ends in a retained node
            earliest_retained_successors[node] = (((), node),)
        else:
            # path always ends in a retained node
            earliest_retained_successors[node] = tuple(
                ((node, *path_to_retained_successor), retained_successor)
                for successor in dag.successors(node)
                for path_to_retained_successor, retained_successor in earliest_retained_successors[successor]
            )
    
    new_graph: networkx.DiGraph[_Node] = networkx.DiGraph()
    for node, node_data in dag.nodes(data=True):
        if node in retained_nodes:
            # Need to add node directly, in case node is disconnected from everyone
            new_graph.add_node(node, **node_data)

            # Now add edges to retained predecessors/successors
            for predecessor in dag.predecessors(node):
                for path, retained_predecessor in latest_retained_predecessors[predecessor]:
                    assert not any(node in retained_nodes for node in path)
                    assert retained_predecessor in retained_nodes
                    path = (retained_predecessor, *path, node)
                    assert networkx.is_path(dag, path)
                    new_graph.add_edge(retained_predecessor, node, **edge_data(dag, path))

            for successor in dag.successors(node):
                for path, retained_successor in earliest_retained_successors[successor]:
                    assert not any(node in retained_nodes for node in path)
                    assert retained_successor in retained_nodes
                    path = (node, *path, retained_successor)
                    assert networkx.is_path(dag, path)
                    new_graph.add_edge(node, retained_successor, **edge_data(dag, path))

    assert set(new_graph.nodes()) == retained_nodes

    return new_graph


def create_digraph(
        nodes: It[_Node | tuple[_Node, dict[str, typing.Any]]],
        edges: It[tuple[_Node, _Node] | tuple[_Node, _Node, dict[str, typing.Any]]],
) -> networkx.DiGraph[_Node]:
    output: "networkx.DiGraph[_Node]" = networkx.DiGraph()
    output.add_nodes_from(nodes)
    output.add_edges_from(edges)
    return output


def would_create_cycle(
        dag: networkx.DiGraph[_Node],
        src: _Node,
        dst: _Node,
) -> bool:
    return src in set(networkx.descendants(dag, dst))


def remove_self_edges(
        graph: networkx.DiGraph[_Node],
) -> networkx.DiGraph[_Node]:
    for src, dst in list(graph.edges()):
        if src == dst:
            graph.remove_edge(src, dst)
    return graph
