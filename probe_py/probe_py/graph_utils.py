from __future__ import annotations
import dataclasses
import functools
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
        assert all_prior(self.dag_tc, self.upper_bound, self.lower_bound)
        assert all_after(self.dag_tc, self.upper_bound, self.lower_bound)
        assert is_antichain(self.dag_tc, self.upper_bound), f"{self.upper_bound} is not an antichain"
        assert is_antichain(self.dag_tc, self.lower_bound), f"{self.lower_bound} is not an antichain"

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

            sorted_union_of_upper_bounds = sorted({
                node
                for segment in segments
                for node in segment.upper_bound
            }, key=functools.cmp_to_key(dag_tc_leq(dag_tc)))

            upper_bound_of_union = set()
            upper_bounded_nodes = set[_Node]()
            for node in sorted_union_of_upper_bounds:
                if node not in upper_bounded_nodes:
                    upper_bound_of_union.add(node)
                    upper_bounded_nodes.update(dag_tc.successors(node))

            sorted_union_of_lower_bounds = sorted({
                node
                for segment in segments
                for node in segment.lower_bound
            }, key=functools.cmp_to_key(dag_tc_leq(dag_tc)), reverse=True)

            lower_bound_of_union = set()
            lower_bounded_nodes = set[_Node]()
            for node in sorted_union_of_lower_bounds:
                if node not in lower_bounded_nodes:
                    lower_bound_of_union.add(node)
                    lower_bounded_nodes.update(dag_tc.predecessors(node))

            return Segment(dag_tc, frozenset(upper_bound_of_union), frozenset(lower_bound_of_union))
        else:
            return Segment(networkx.DiGraph(), frozenset(), frozenset())

def dag_tc_leq(dag_tc: networkx.DiGraph[_Node]) -> typing.Callable[[_Node, _Node], bool]:
    """Return a less-than-or-equal-to operator for the transitive closure of a DAG."""
    def leq(node0: _Node, node1: _Node) -> bool:
        return node0 == node1 or node0 in dag_tc.predecessors(node1)
    return leq


def get_bottommost(dag_tc: networkx.DiGraph[_Node], nodes: typing.Iterable[_Node]) -> frozenset[_Node]:
    covered_nodes = set[_Node]()
    bottommost_nodes = set()
    sorted_nodes = sorted(nodes, key=functools.cmp_to_key(dag_tc_leq(dag_tc)), reverse=False)
    serialize_graph(dag_tc, pathlib.Path("test2.dot"))
    for a, b in zip(sorted_nodes[:-1], sorted_nodes[1:]):
        print(a, b, dag_tc_leq(dag_tc)(a, b), a in dag_tc.predecessors(b))
    for node in sorted_nodes:
        if node not in covered_nodes:
            bottommost_nodes.add(node)
            covered_nodes.update(dag_tc.predecessors(node))
            print(bottommost_nodes, [other for other in nodes if other in covered_nodes])
    return frozenset(bottommost_nodes)


def get_uppermost(dag_tc: networkx.DiGraph[_Node], nodes: typing.Iterable[_Node]) -> frozenset[_Node]:
    covered_nodes = set[_Node]()
    uppermost_nodes = set()
    sorted_nodes = sorted(nodes, key=functools.cmp_to_key(dag_tc_leq(dag_tc)), reverse=True)
    for node in sorted_nodes:
        if node not in covered_nodes:
            uppermost_nodes.add(node)
            covered_nodes.update(dag_tc.successors(node))
    return frozenset(uppermost_nodes)


def poset_to_dag(
        elements: typing.Iterable[_Node],
        leq: typing.Callable[[_Node, _Node], bool],
        self_loops: bool = False,
) -> networkx.DiGraph[_Node]:
    dag: networkx.DiGraph[_Node] = networkx.DiGraph()
    for e0, e1 in itertools.product(elements, repeat=2):
        if (self_loops or e0 != e1) and leq(e0, e1):
            dag.add_edge(e0, e1)
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
    relabeling = {node: name_mapper(node) for node in graph.nodes()}
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


def all_prior(
        reflexive_transitive_closure: networkx.DiGraph[_Node],
        antichain0: typing.Iterable[_Node],
        antichain1: typing.Iterable[_Node],
) -> bool:
    """All of antichain0 is before any of antichain1"""
    return all(
        any(
            antichain0_node in reflexive_transitive_closure.predecessors(antichain1_node)
            for antichain1_node in antichain1
        )
        for antichain0_node in antichain0
    )


def all_after(
        reflexive_transitive_closure: networkx.DiGraph[_Node],
        antichain0: typing.Iterable[_Node],
        antichain1: typing.Iterable[_Node],
) -> bool:
    """All of antichain1 is after some of antichain0"""
    return all(
        any(
            antichain0_node in reflexive_transitive_closure.predecessors(antichain1_node)
            for antichain0_node in antichain0
        )
        for antichain1_node in antichain1
    )

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
