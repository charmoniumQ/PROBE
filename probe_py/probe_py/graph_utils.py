from __future__ import annotations
import itertools
import typing
import pathlib
import networkx
from typing import Optional
import pydot


_Node = typing.TypeVar("_Node")


if typing.TYPE_CHECKING:
    DiGraph: typing.TypeAlias = networkx.DiGraph
else:
    DiGraph = networkx.DiGraph


def serialize_graph(
        graph: DiGraph[_Node],
        output: pathlib.Path,
) -> None:
    pydot_graph = networkx.drawing.nx_pydot.to_pydot(graph)
    if output.suffix == ".dot":
        pydot_graph.write_raw(output)
    else:
        pydot_graph.write_png(output)

def serialize_graph_proc_tree(
    graph: DiGraph[_Node],
    output: pathlib.Path,
    same_rank_groups: Optional[list[list[str]]] = None,
) -> None:
    """
    Serialize a DiGraph to .dot or .png, optionally forcing certain node groups
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
        reflexive_transitive_closure: DiGraph[_Node],
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
        reflexive_transitive_closure: DiGraph[_Node],
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


def is_valid_segment(
        reflexive_transitive_closure: DiGraph[_Node],
        upper_bound_inclusive: frozenset[_Node],
        lower_bound_inclusive: frozenset[_Node],
) -> bool:
    return (all_prior(reflexive_transitive_closure, upper_bound_inclusive, lower_bound_inclusive)
        and
        all_after(reflexive_transitive_closure, upper_bound_inclusive, lower_bound_inclusive)
    )


def add_self_loops(
        digraph: DiGraph[_Node],
        copy: bool,
) -> DiGraph[_Node]:
    if copy:
        digraph = digraph.copy()
    for node in digraph.nodes():
        digraph.add_edge(node, node)
    return digraph


def nodes_in_segment(
        reflexive_transitive_closure: DiGraph[_Node],
        upper_bound_inclusive: frozenset[_Node],
        lower_bound_inclusive: frozenset[_Node],
) -> frozenset[_Node]:
    candidates = frozenset(itertools.chain.from_iterable(
        reflexive_transitive_closure.successors(upper_bound)
        for upper_bound in upper_bound_inclusive
    ))
    return frozenset({
        candidate
        for candidate in candidates
        if any(
                lower_bound in reflexive_transitive_closure.successors(candidate)
                for lower_bound in lower_bound_inclusive
        )
    })


def replace(digraph: DiGraph[_Node], old: _Node, new: _Node) -> None:
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
