from __future__ import annotations
import collections.abc
import dataclasses
import tqdm
import itertools
import typing
import pathlib
import networkx
import pydot
from . import util


_Node = typing.TypeVar("_Node")


@dataclasses.dataclass(frozen=True)
class Segment(typing.Generic[_Node]):
    dag_tc: networkx.DiGraph[_Node]
    upper_bound: frozenset[_Node]
    lower_bound: frozenset[_Node]

    def __post_init__(self) -> None:
        unbounded = unbounded_below_nodes(self.dag_tc, self.upper_bound, self.lower_bound)
        assert not unbounded, \
            f"{unbounded} in self.upper_bound is not dominated by any in {self.lower_bound=}"
        unbounded = unbounded_above_nodes(self.dag_tc, self.lower_bound, self.upper_bound)
        assert not unbounded, \
            f"{unbounded} in self.lower_bound is not dominated by any in {self.upper_bound=}"
        assert is_antichain(self.dag_tc, self.upper_bound), \
            f"{self.upper_bound} is not an antichain"
        assert is_antichain(self.dag_tc, self.lower_bound), \
            f"{self.lower_bound} is not an antichain"

    def nodes(self) -> frozenset[_Node]:
        beneath_upper_bound = frozenset(
            itertools.chain.from_iterable(
                self.dag_tc.successors(node)
                for node in self.upper_bound
            )
        )
        above_lower_bound = frozenset(
            itertools.chain.from_iterable(
                self.dag_tc.predecessors(node)
                for node in self.lower_bound
            )
        )
        return beneath_upper_bound & above_lower_bound

    def overlaps(self, other: Segment[_Node]) -> bool:
        assert self.dag_tc is other.dag_tc
        return bool(self.nodes() & other.nodes())

    @staticmethod
    def union(segments: typing.Sequence[Segment[_Node]]) -> Segment[_Node]:
        if segments:
            dag_tc = segments[0].dag_tc
            assert all(segment.dag_tc is dag_tc for segment in segments)

            sorted_union_of_upper_bounds = dag_sort(dag_tc, {
                node
                for segment in segments
                for node in segment.upper_bound
            })

            upper_bound_of_union = set()
            upper_bounded_nodes = set[_Node]()
            for node in sorted_union_of_upper_bounds:
                if node not in upper_bounded_nodes:
                    upper_bound_of_union.add(node)
                    upper_bounded_nodes.update(dag_tc.successors(node))

            sorted_union_of_lower_bounds = dag_sort(dag_tc, {
                node
                for segment in segments
                for node in segment.lower_bound
            }, reverse=True)

            lower_bound_of_union = set()
            lower_bounded_nodes = set[_Node]()
            for node in sorted_union_of_lower_bounds:
                if node not in lower_bounded_nodes:
                    lower_bound_of_union.add(node)
                    lower_bounded_nodes.update(dag_tc.predecessors(node))

            return Segment(dag_tc, frozenset(upper_bound_of_union), frozenset(lower_bound_of_union))
        else:
            return Segment(networkx.DiGraph(), frozenset(), frozenset())


def dag_sort(
        dag_tc: networkx.DiGraph[_Node],
        nodes: typing.Iterable[_Node],
        reverse: bool = False,
        check: bool = True,
) -> list[_Node]:
    # NOT CORRECT!
    # TIL: Can't use traditional sorting algorithms for partial orders.
    # ret = sorted(nodes, key=functools.cmp_to_key(dag_tc_leq(dag_tc, reverse=reverse)))
    return list(networkx.topological_sort(hasse_diagram(
        nodes,
        lambda n0, n1: dag_tc.has_edge(n1, n0) if reverse else dag_tc.has_edge(n0, n1),
    )))


def get_bottommost(dag_tc: networkx.DiGraph[_Node], nodes: collections.abc.Set[_Node]) -> frozenset[_Node]:
    covered_nodes = set[_Node]()
    bottommost_nodes = set()
    sorted_nodes = dag_sort(dag_tc, nodes, reverse=True)
    for node in sorted_nodes:
        if node not in covered_nodes:
            bottommost_nodes.add(node)
            covered_nodes.update(dag_tc.predecessors(node))
    return frozenset(bottommost_nodes)


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


def serialize_graph(
        graph: networkx.DiGraph[_Node],
        output: pathlib.Path,
        name_mapper: typing.Callable[[_Node], str] | None = None,
) -> None:
    graph2: networkx.DiGraph[_Node] | networkx.DiGraph[str]
    if name_mapper is None:
        def name_mapper(node: _Node) -> str:
            return str(node)
    relabeling = {node: name_mapper(node) for node in tqdm.tqdm(graph.nodes(), "relabel nodes")}
    assert util.all_unique(relabeling.values()), util.duplicates(relabeling.values())
    graph2 = networkx.relabel_nodes(graph, relabeling)
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


def unbounded_below_nodes(
        reflexive_transitive_closure: networkx.DiGraph[_Node],
        candidates: typing.Iterable[_Node],
        bounds: typing.Iterable[_Node],
) -> list[_Node]:
    """Return all candidates which are not bounded below by bounds"""
    return [
        candidate
        for candidate in candidates
        if not any(
            reflexive_transitive_closure.has_edge(candidate, bound) or candidate == bound
            for bound in bounds
        )
    ]


def unbounded_above_nodes(
        reflexive_transitive_closure: networkx.DiGraph[_Node],
        candidates: typing.Iterable[_Node],
        bounds: typing.Iterable[_Node],
) -> list[_Node]:
    """Return all candidates which are not bounded above by bounds"""
    return [
        candidate
        for candidate in candidates
        if not any(
            reflexive_transitive_closure.has_edge(bound, candidate) or candidate == bound
            for bound in bounds
        )
    ]

def is_antichain(
        reflexive_transitive_closure: networkx.DiGraph[_Node],
        nodes: typing.Iterable[_Node],
) -> bool:
    """An antichain is a set of nodes where neither dominates the other."""
    return all(
        node0 not in reflexive_transitive_closure.successors(node1) and node1 not in reflexive_transitive_closure.successors(node0)
        for node0, node1 in itertools.combinations(nodes, 2)
    )


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
