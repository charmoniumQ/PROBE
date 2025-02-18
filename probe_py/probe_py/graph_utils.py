import typing
import pathlib
import networkx  # type: ignore
from typing import Optional
import pydot  # type: ignore


_Node = typing.TypeVar("_Node")


if typing.TYPE_CHECKING:
    DiGraph: typing.TypeAlias = networkx.DiGraph[_Node]
else:
    class DiGraph(typing.Generic[_Node], networkx.DiGraph):
        pass


def serialize_graph(
        graph: DiGraph[_Node],
        output: pathlib.Path,
) -> None:
    pydot_graph = networkx.drawing.nx_pydot.to_pydot(graph)
    if output.suffix == "dot":
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
        pydot_graph.write_raw(str(output))
    else:
        pydot_graph.write_png(str(output))


def relax_node(graph: DiGraph[_Node], node: _Node) -> list[tuple[_Node, _Node]]:
    """Remove node from graph and attach its predecessors to its successors"""
    ret = list[tuple[typing.Any, typing.Any]]()
    for predecessor in graph.predecessors(node):
        for successor in graph.successors(node):
            ret.append((predecessor, successor))
            graph.add_edge(predecessor, successor)
    graph.remove_node(node)
    return ret


def list_edges_from_start_node(graph: DiGraph[_Node], start_node: _Node) -> typing.Iterable[tuple[_Node, _Node]]:
    all_edges = list(graph.edges())
    start_index = next(i for i, edge in enumerate(all_edges) if edge[0] == start_node)
    ordered_edges = all_edges[start_index:] + all_edges[:start_index]
    return ordered_edges
