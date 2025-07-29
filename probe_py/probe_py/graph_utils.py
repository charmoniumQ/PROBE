from __future__ import annotations
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
    dag_tc: LazyTransitiveClosure[_CoNode]
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

    def nodes(self) -> frozenset[_CoNode]:
        return self.dag_tc.between(self.upper_bound, self.lower_bound)

    def overlaps(self, other: Segment[_CoNode]) -> bool:
        assert self.dag_tc is other.dag_tc
        return bool(self.nodes() & other.nodes())

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
        name_mapper: typing.Callable[[_Node], str] = str,
) -> None:
    graph2 = map_nodes(name_mapper, graph)
    pydot_graph = networkx.drawing.nx_pydot.to_pydot(graph2)
    if output.suffix == ".dot":
        pydot_graph.write_raw(output)
    else:
        pydot_graph.write_png(output)

def serialize_graph_proc_tree(
    graph: networkx.DiGraph[_Node],
    output: pathlib.Path,
    same_rank_groups: list[list[str]] | None = None,
) -> None:
    """
    Serialize a networkx.DiGraph to .dot or .png, optionally forcing certain node groups
    to share the same rank.
    """
    pydot_graph = networkx.drawing.nx_pydot.to_pydot(graph)
    pydot_graph.set("rankdir", "TB")

    if same_rank_groups:
        for idx, group in enumerate(same_rank_groups):
            subg = pydot.Subgraph('', rank='same')

            for node_id in group:
                existing_nodes = pydot_graph.get_node(node_id)
                if existing_nodes:
                    subg.add_node(existing_nodes[0])

            pydot_graph.add_subgraph(subg)

    if output.suffix == ".dot":
        pydot_graph.write_raw(output)
    else:
        pydot_graph.write_png(output)


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
) -> typing.Generator[_Node, bool, None]:
    """BFS but send False to prune this branch"""
    queue = [start]
    while queue:
        node = queue.pop()
        continue_with_children = yield node
        if continue_with_children:
            queue.extend(digraph.successors(node))


def get_root(dag: networkx.DiGraph[_Node]) -> _Node:
    roots = get_roots(dag)
    if len(roots) != 1:
        raise RuntimeError(f"No roots or too many roots: {roots}")
    else:
        return roots[0]


def get_roots(dag: networkx.DiGraph[_Node]) -> list[_Node]:
    return [
        node
        for node in dag.nodes()
        if dag.in_degree(node) == 0
    ]


def randomly_sample_edges(inp: networkx.DiGraph[_Node], factor: float, seed: int = 0) -> networkx.DiGraph[_Node]:
    out: networkx.DiGraph[_Node] = networkx.DiGraph()
    rng = random.Random(seed)
    inp_edges = list(inp.edges(data=True))
    for src, dst, data in rng.sample(inp_edges, round(len(inp_edges) * factor)):
        out.add_edge(src, dst, **data)
    return out


class LazyTransitiveClosure(typing.Generic[_Node]):
    _dag: networkx.DiGraph[_Node]
    _topological_generations: list[list[_Node]]
    _rank: typing.Mapping[_Node, int]
    _descendants: dict[_Node, tuple[int, set[_Node]]]

    def __init__(self, dag: networkx.DiGraph[_Node]) -> None:
        self._dag = dag
        self._topological_generations = [
            list(layer)
            for layer in networkx.topological_generations(self._dag)
        ]
        self._rank = {
            node: layer_no
            for layer_no, layer in enumerate(self._topological_generations)
            for node in layer
        }
        self._descendants = {}

    def between(self, upper_bounds: frozenset[_Node], lower_bounds: frozenset[_Node]) -> frozenset[_Node]:
        max_rank = max(self._rank[lower_bound] for lower_bound in lower_bounds)
        descendants = set().union(*(
            self.descendants(upper_bound, max_rank)
            for upper_bound in upper_bounds
        ))
        return frozenset({
            node
            for node in descendants
            if self.descendants(node, max_rank) & lower_bounds
        })

    def non_ancestors(self, candidates: frozenset[_Node], lower_bound: frozenset[_Node]) -> frozenset[_Node]:
        max_rank = max(self._rank[bound] for bound in lower_bound)
        return frozenset({
            candidate
            for candidate in candidates - lower_bound
            if not self.descendants(candidate, max_rank) & lower_bound
        })

    def non_descendants(self, candidates: frozenset[_Node], upper_bound: frozenset[_Node]) -> frozenset[_Node]:
        max_rank = max(self._rank[candidate] for candidate in candidates)
        descendants = set().union(*(
            self.descendants(upper_bound, max_rank)
            for upper_bound in upper_bound
        ))
        return frozenset(candidates - descendants - upper_bound)

    def is_antichain(self, nodes: typing.Iterable[_Node]) -> bool:
        max_rank = max(self._rank[node] for node in nodes)
        return all(
            node0 not in self.descendants(node1, max_rank) and node1 not in self.descendants(node0, max_rank)
            for node0, node1 in itertools.combinations(nodes, 2)
        )

    def get_bottommost(self, nodes: collections.abc.Set[_Node]) -> frozenset[_Node]:
        max_rank = max(self._rank[node] for node in nodes)
        bottommost_nodes = set[_Node]()
        sorted_nodes = self.sorted(nodes)[::-1]
        for node in sorted_nodes:
            if not self.descendants(node, max_rank) & bottommost_nodes:
                bottommost_nodes.add(node)
        return frozenset(bottommost_nodes)

    def get_uppermost(self, nodes: collections.abc.Set[_Node]) -> frozenset[_Node]:
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
                        set.union(*(descendants[successor][1] for successor in successors_in_range)) if successors_in_range else set(),
                    )

        return frozenset(descendants[node][1])


def dag_transitive_closure(dag: networkx.DiGraph[_Node]) -> networkx.DiGraph[_Node]:
    tc: networkx.DiGraph[_Node] = networkx.DiGraph()
    node_order = list(networkx.topological_sort(dag))[::-1]
    for src in tqdm.tqdm(node_order, desc="TC"):
        tc.add_node(src)
        for child in dag.successors(src):
            tc.add_edge(src, child)
            for grandchild in dag.successors(child):
                tc.add_edge(src, grandchild)
    return tc
