from __future__ import annotations
import abc
import collections
import dataclasses
import functools
import itertools
import typing
import pathlib
import frozendict
import networkx
import pydot
import tqdm
from . import util


_Node = typing.TypeVar("_Node")
_Node2 = typing.TypeVar("_Node2")
_T_co = typing.TypeVar("_T_co", covariant=True)
_V_co = typing.TypeVar("_V_co", covariant=True)
FrozenDict: typing.TypeAlias = frozendict.frozendict[_T_co, _V_co]
EdgeData = typing.Mapping[str, typing.Any]
It: typing.TypeAlias = collections.abc.Iterable[_T_co]


@dataclasses.dataclass(frozen=True)
class Interval(typing.Generic[_Node]):
    upper_bound: frozenset[_Node]
    lower_bound: frozenset[_Node]

    def __post_init__(self) -> None:
        assert self.upper_bound
        assert self.lower_bound
        # assert self.dag_tc.is_antichain(self.upper_bound), \
        #     f"{self.upper_bound} is not an antichain"
        # assert self.dag_tc.is_antichain(self.lower_bound), \
        #     f"{self.lower_bound} is not an antichain"
        # unbounded = self.dag_tc.non_ancestors(self.upper_bound, self.lower_bound)
        # assert not unbounded, \
        #     f"{unbounded} in self.upper_bound is not an ancestor of any any in {self.lower_bound=}"
        # unbounded = self.dag_tc.non_descendants(self.lower_bound, self.upper_bound)
        # assert not unbounded, \
        #     f"{unbounded} in self.lower_bound is not a descendant of any in {self.upper_bound=}"

    @staticmethod
    def singleton(_dag_tc: ReachabilityOracle[_Node], node: _Node) -> Interval[_Node]:
        return Interval(frozenset({node}), frozenset({node}))

    def __bool__(self) -> bool:
        "Whether the interval is non-empty"
        return bool(self.upper_bound)

    @staticmethod
    def union(dag_tc: ReachabilityOracle[_Node], *intervals: Interval[_Node]) -> Interval[_Node]:
        assert intervals
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
        return Interval(frozenset(upper_bound), frozenset(lower_bound))

    def all_greater_than(self, dag_tc: ReachabilityOracle[_Node], other: Interval[_Node]) -> bool:
        other_upper_bounds_that_are_not_descendent_of_self_lower_bounds = \
            dag_tc.non_descendants(other.upper_bound, self.lower_bound)
        return not other_upper_bounds_that_are_not_descendent_of_self_lower_bounds


def map_nodes(
        mapper: typing.Callable[[_Node], _Node2],
        graph: networkx.DiGraph[_Node],
        check: bool = True,
) -> networkx.DiGraph[_Node2]:
    dct = {node: mapper(node) for node in tqdm.tqdm(graph.nodes(), desc="map nodes", total=len(graph.nodes()))}
    assert util.all_unique(dct.values()), list(dct.values())
    ret = typing.cast("networkx.DiGraph[_Node2]", networkx.relabel_nodes(graph, dct))
    return ret


def filter_nodes(
        predicate: typing.Callable[[_Node], bool],
        graph: networkx.DiGraph[_Node],
) -> networkx.DiGraph[_Node]:
    # Set for fast containment-check
    kept_nodes_set = set()
    # List to preserve order of the original graph
    kept_nodes_list = []
    for node in graph.nodes():
        if node not in kept_nodes_set:
            kept_nodes_set.add(node)
            kept_nodes_list.append(node)
    return create_digraph(
        kept_nodes_list,
        [
            (src, dst)
            for src, dst in tqdm.tqdm(graph.edges(), desc="filter edges", total=len(graph.edges()))
            if src in kept_nodes_set and dst in kept_nodes_set
        ]
    )


def serialize_graph(
        graph: networkx.DiGraph[_Node],
        output: pathlib.Path,
        id_mapper: typing.Callable[[_Node], str] | None = None,
        cluster_labels: collections.abc.Mapping[str, str] = {},
) -> None:
    if id_mapper is None:
        def id_mapper(node: _Node) -> str:
            data = graph.nodes(data=True)[node]
            if "id" in data:
                id = data["id"]
                del data["id"]
            else:
                id = node
            return str(id)
    graph2 = map_nodes(id_mapper, graph)

    if output.suffix.endswith("dot"):
        pydot_graph = networkx.drawing.nx_pydot.to_pydot(graph2)
        pydot_graph.set("rankdir", "TB")
        clusters = dict[str, pydot.Subgraph]()
        for node in sorted(pydot_graph.get_nodes(), key=str):
            cluster_name = node.get("cluster")
            if cluster_name:
                if cluster_name not in clusters:
                    cluster_subgraph = pydot.Subgraph(
                        f"cluster_{cluster_name}",
                        label=cluster_labels.get(cluster_name, cluster_name),
                    )
                    pydot_graph.add_subgraph(cluster_subgraph)
                    clusters[cluster_name] = cluster_subgraph
                cluster_subgraph = clusters[cluster_name]
                cluster_subgraph.add_node(node)
        pydot_graph.write(str(output), "raw")
    elif output.suffix.endswith("graphml"):
        networkx.write_graphml(graph2, output)
    else:
        raise ValueError("Unknown output type")


def search_with_pruning(
        digraph: networkx.DiGraph[_Node],
        start: _Node,
        breadth_first: bool = True,
        sort_nodes: typing.Callable[[list[_Node]], list[_Node]] = lambda lst: lst,
) -> typing.Generator[_Node | None, bool | None, None]:
    """DFS/BFS but send False to prune this branch

        traversal = bfs_with_pruning
        for node in traversal:
            assert node is not None
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
    def add_edge(self, u: _Node, v: _Node) -> None:
        """Keep datastructure up-to-date"""

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
        assert self.is_antichain(upper_bound), f"{upper_bound} is not an antichain"
        assert self.is_antichain(lower_bound), f"{lower_bound} is not an antichain"
        unbounded = self.non_ancestors(upper_bound, lower_bound)
        assert not unbounded, \
            f"{unbounded} in self.upper_bound is not an ancestor of any any in {lower_bound=}"
        unbounded = self.non_descendants(lower_bound, upper_bound)
        assert not unbounded, \
            f"{unbounded} in self.lower_bound is not a descendant of any in {upper_bound=}"
        return Interval(upper_bound, lower_bound)


@dataclasses.dataclass(frozen=False)
class LazyRankReachabilityOracle(ReachabilityOracle[_Node]):
    _dag: networkx.DiGraph[_Node]
    _rank: typing.Mapping[_Node, int]
    _descendants: dict[_Node, tuple[int, frozenset[_Node]]]

    @staticmethod
    def create(dag: networkx.DiGraph[_Node]) -> LazyRankReachabilityOracle[_Node]:
        topological_generations = [
            list(layer)
            for layer in networkx.topological_generations(dag)
        ]
        rank = {
            node: layer_no
            for layer_no, layer in enumerate(topological_generations)
            for node in layer
        }
        return LazyRankReachabilityOracle(dag, rank, {})

    def __contains__(self, node: _Node) -> bool:
        return node in self._dag

    def non_ancestors(self, candidates: It[_Node], lower_bound: It[_Node]) -> frozenset[_Node]:
        lower_bound_set = frozenset(lower_bound)
        max_rank = max(self._rank[bound] for bound in lower_bound)
        return frozenset({
            candidate
            for candidate in frozenset(candidates) - lower_bound_set
            if not self.descendants(candidate, max_rank) & lower_bound_set
        })

    def non_descendants(self, candidates: It[_Node], upper_bound: It[_Node]) -> frozenset[_Node]:
        max_rank = max(self._rank[candidate] for candidate in candidates)
        descendants = frozenset().union(*(
            self.descendants(upper_bound, max_rank)
            for upper_bound in upper_bound
        ))
        return frozenset(frozenset(candidates) - descendants - frozenset(upper_bound))

    def is_antichain(self, nodes: typing.Iterable[_Node]) -> bool:
        max_rank = max(self._rank[node] for node in nodes)
        return all(
            node0 not in self.descendants(node1, max_rank) and node1 not in self.descendants(node0, max_rank)
            for node0, node1 in itertools.combinations(nodes, 2)
        )

    def get_bottommost(self, nodes: It[_Node]) -> frozenset[_Node]:
        max_rank = max(self._rank[node] for node in nodes)
        bottommost_nodes = set[_Node]()
        sorted_nodes = self.sorted(nodes)[::-1]
        for node in sorted_nodes:
            if not self.descendants(node, max_rank) & bottommost_nodes:
                bottommost_nodes.add(node)
        return frozenset(bottommost_nodes)

    def get_uppermost(self, nodes: It[_Node]) -> frozenset[_Node]:
        max_rank = max(self._rank[node] for node in nodes)
        uppermost_nodes = set[_Node]()
        covered_nodes = set[_Node]()
        sorted_nodes = self.sorted(nodes)
        for node in sorted_nodes:
            if node not in covered_nodes:
                uppermost_nodes.add(node)
                covered_nodes.update(self.descendants(node, max_rank))
        return frozenset(uppermost_nodes)

    def sorted(self, nodes: typing.Iterable[_Node]) -> list[_Node]:
        return sorted(nodes, key=self._rank.__getitem__)

    def is_reachable(self, src: _Node, dst: _Node) -> bool:
        return dst in self.descendants(src, self._rank[dst])

    def descendants(self, src: _Node, rank: int) -> frozenset[_Node]:
        # Read the code as if descendants is True.
        # Note that everythign is exactly reversed if descendants was false.
        descendants = self._descendants
        successors = self._dag.successors
        def in_range(input_rank: int) -> bool:
            return input_rank <= rank

        # stack will hold _paths from src_ not nodes
        stack = [
            [src]
        ]

        # Do DFS
        while stack:
            path = stack[-1]
            assert path[0] == src
            node = path[-1]
            if node in descendants and in_range(descendants[node][0]):
                # already pre-computed, no work to do.
                stack.pop()
            else:
                # Not already precomputed
                # Recurse into successors
                # But only those in range
                successors_in_range = {
                    successor
                    for successor in successors(node)
                    if in_range(self._rank[successor])
                }
                noncomputed_successors_in_range = {
                    successor
                    for successor in successors_in_range
                    if successor not in descendants[successor][1] or not in_range(descendants[successor][0])
                }
                if noncomputed_successors_in_range:
                    for successor in noncomputed_successors_in_range:
                        stack.append([*path, successor])
                else:
                    descendants[node] = (
                        rank,
                        frozenset.union(*(descendants[successor][1] for successor in successors_in_range)) if successors_in_range else frozenset(),
                    )
        return frozenset(descendants[node][1])

    def add_edge(self, source: _Node, target: _Node) -> None:
        raise NotImplementedError()

    @functools.cache
    def n_paths(self, source: _Node, destination: _Node) -> int:
        raise NotImplementedError()


@dataclasses.dataclass(frozen=False)
class LazyReachabilityOracle(ReachabilityOracle[_Node]):
    dag: networkx.DiGraph[_Node]
    descendants: dict[_Node, frozenset[_Node]]

    @staticmethod
    def create(dag: networkx.DiGraph[_Node]) -> LazyReachabilityOracle[_Node]:
        return LazyReachabilityOracle(dag, {})

    def __contains__(self, node: _Node) -> bool:
        return node in self.dag

    def _get_descendants(self, root: _Node) -> frozenset[_Node]:
        if root in self.descendants:
            return self.descendants[root]

        stack = [root]
        visited = set()
        postorder = []  # To process nodes after their children

        # DFS traversal
        while stack:
            curr = stack.pop()
            if curr in visited:
                postorder.append(curr)
                continue
            visited.add(curr)
            stack.append(curr)  # Mark for post-processing
            for child in self.dag.successors(curr):
                if child not in visited:
                    stack.append(child)

        # Build descendant sets bottom-up
        for n in postorder:
            if n in self.descendants:
                continue
            descendants = set()
            for child in self.dag.successors(n):
                descendants.add(child)
                descendants |= self.descendants.get(child, set())
            self.descendants[n] = frozenset(descendants)

        return self.descendants[root]

    def is_reachable(self, u: _Node, v: _Node) -> bool:
        return v in self._get_descendants(u) or u == v

    def add_edge(self, source: _Node, target: _Node) -> None:
        raise NotImplementedError()

    def n_paths(self, source: _Node, destination: _Node) -> int:
        raise NotImplementedError()


@dataclasses.dataclass(frozen=True)
class PrecomputedReachabilityOracle(ReachabilityOracle[_Node]):
    dag: networkx.DiGraph[_Node]
    dag_tc: networkx.DiGraph[_Node]

    @staticmethod
    def create(dag: networkx.DiGraph[_Node], progress: bool = False) -> PrecomputedReachabilityOracle[_Node]:
        tc: networkx.DiGraph[_Node] = networkx.DiGraph()
        node_order = list(networkx.topological_sort(dag))[::-1]
        for src in tqdm.tqdm(node_order, desc="TC nodes", disable=not progress):
            tc.add_node(src)
            for child in dag.successors(src):
                tc.add_edge(src, child)
                for grandchild in tc.successors(child):
                    tc.add_edge(src, grandchild)
        return PrecomputedReachabilityOracle(
            dag,
            tc,
        )

    def __contains__(self, node: _Node) -> bool:
        return node in self.dag_tc

    def is_reachable(self, u: _Node, v: _Node) -> bool:
        return v in self.dag_tc.successors(u) or u == v

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
    non_combinable_nodes = list()
    for node in graph.nodes():
        if combinable(node):
            preds = frozenset(graph.predecessors(node))
            succs = frozenset(graph.successors(node))
            neighbors_to_node.setdefault((preds, succs), []).append(node)
        else:
            non_combinable_nodes.append(node)
    partitions_list = [
        # Order of partitions shoudl be deterministic to make the resulting graph deterministically ordered
        *map(frozenset, neighbors_to_node.values()),
        *map(lambda node: frozenset({node}), non_combinable_nodes),
    ]

    quotient = typing.cast(
        "networkx.DiGraph[frozenset[_Node]]",
        networkx.quotient_graph(graph, partitions_list),
    )
    for _, data in quotient.nodes(data=True):
        del data["nnodes"]
        del data["density"]
        del data["graph"]
        del data["nedges"]
    for _, _, data in quotient.edges(data=True):
        del data["weight"]
    return quotient


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
    for node in nodes:
        if isinstance(node, tuple) and len(node) == 2 and isinstance(node[1], dict) and all(isinstance(key, str) for key in node[1]):
            output.add_node(node[0], **node[1])
        else:
            output.add_node(node)  # type: ignore
    for edge in edges:
        if isinstance(edge, tuple) and len(edge) == 3 and isinstance(edge[2], dict) and all(isinstance(key, str) for key in edge[2]):
            output.add_edge(edge[0], edge[1], **edge[2])
        else:
            output.add_edge(edge[0], edge[1])
    return output


def would_create_cycle(
        dag: networkx.DiGraph[_Node],
        src: _Node,
        dst: _Node,
) -> bool:
    for desc in networkx.descendants(dag, dst):
        if desc == src:
            return True
    return False


def remove_self_edges(
        graph: networkx.DiGraph[_Node],
) -> networkx.DiGraph[_Node]:
    for src, dst in list(graph.edges()):
        if src == dst:
            graph.remove_edge(src, dst)
    return graph
