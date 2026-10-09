from __future__ import annotations

import collections
import itertools
import typing

import charmonium.time_block
import networkx as nx
import pydot

from . import priority_queue, util

if typing.TYPE_CHECKING:
    import pathlib

_Node = typing.TypeVar("_Node", bound=typing.Hashable)
_Node2 = typing.TypeVar("_Node2", bound=typing.Hashable)
_T_co = typing.TypeVar("_T_co", covariant=True)
EdgeData = typing.Mapping[str, typing.Any]
It: typing.TypeAlias = collections.abc.Iterable[_T_co]


def map_nodes(
    mapper: typing.Callable[[_Node], _Node2],
    graph: nx.DiGraph[_Node],
    *,
    check_unique: bool = True,
) -> nx.DiGraph[_Node2]:
    if check_unique:
        dups = util.duplicates(graph.nodes(), mapper)
        assert not dups, dups
    dct = {node: mapper(node) for node in graph.nodes()}
    return typing.cast("nx.DiGraph[_Node2]", nx.relabel_nodes(graph, dct))


def relax_node(graph: nx.DiGraph[_Node], node: _Node) -> None:
    for predecessor, successor in itertools.product(
        graph.predecessors(node),
        graph.successors(node),
    ):
        graph.add_edge(predecessor, successor)
    graph.remove_node(node)


def serialize_graph(
    graph: nx.DiGraph[_Node],
    output: pathlib.Path,
    id_mapper: typing.Callable[[_Node], str] | None = None,
    cluster_labels: collections.abc.Mapping[str, str] = {},
) -> None:
    if id_mapper is None:

        def id_mapper(node: _Node) -> str:
            data = graph.nodes(data=True)[node]
            if "id" in data:
                ident = data["id"]
                assert isinstance(ident, str)
            else:
                ident = str(node)
            assert "'" not in ident, ident
            assert '"' not in ident, ident
            assert "\\" not in ident, ident
            return ident

    graph2 = map_nodes(id_mapper, graph)

    for _, data in graph2.nodes(data=True):
        if "id" in data:
            del data["id"]

    if output.suffix.endswith("dot"):
        pydot_graph = nx.drawing.nx_pydot.to_pydot(graph2)
        pydot_graph.set("rankdir", "TB")
        clusters = dict[str, pydot.Subgraph]()
        for dot_node in sorted(pydot_graph.get_nodes(), key=str):
            cluster_name = dot_node.get("cluster")
            if cluster_name:
                if cluster_name not in clusters:
                    cluster_subgraph = pydot.Subgraph(
                        f"cluster_{cluster_name}",
                        label=cluster_labels.get(cluster_name, cluster_name),
                    )
                    pydot_graph.add_subgraph(cluster_subgraph)
                    clusters[cluster_name] = cluster_subgraph
                cluster_subgraph = clusters[cluster_name]
                cluster_subgraph.add_node(dot_node)
        pydot_graph.write(str(output), "raw")
    elif output.suffix.endswith("graphml"):
        nx.write_graphml(graph2, output)
    elif output.suffix.endswith("elk"):
        with output.open("w+") as fobj:
            for _node, data in graph.nodes(data=True):
                label = f'\n  label "{data["label"]}"\n' if data.get("label") else ""
                fobj.write(f"node {data['id']} {{{label}}}\n")
            for src, dst, edge_data in graph.edges(data=True):
                src_id = graph.nodes(data=True)[src]["id"]
                dst_id = graph.nodes(data=True)[dst]["id"]
                color = f"\n  {edge_data['color']}\n" if data.get("color") else ""
                fobj.write(f"edge {src_id} -> {dst_id} {{{color}}}\n")
    else:
        msg = f"Unknown output type {output} ({output.suffix})"
        raise ValueError(msg)


def search_with_pruning(
    digraph: nx.DiGraph[_Node],
    start: _Node,
    *,
    breadth_first: bool = True,
    sort_nodes: typing.Callable[[list[_Node]], list[_Node]] = lambda lst: lst,
) -> typing.Generator[_Node | None, bool | None, None]:
    """
    DFS/BFS but send False to prune this branch.

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


def get_sources(dag: nx.DiGraph[_Node]) -> list[_Node]:
    return [node for node in dag.nodes() if dag.in_degree(node) == 0]


def get_sinks(dag: nx.DiGraph[_Node]) -> list[_Node]:
    return [node for node in dag.nodes() if dag.out_degree(node) == 0]


def topological_sort_depth_first(
    dag: nx.DiGraph[_Node],
    score_children: typing.Callable[[_Node, _Node], int] = lambda _parent, _child: 0,
) -> typing.Iterable[_Node]:
    """Topological sort that breaks ties by depth first, and then by lowest child score."""
    queue = priority_queue.PriorityQueue[_Node, tuple[int, int]](
        (node, (dag.in_degree(node), 0)) for node in dag.nodes()
    )
    counter = 0
    while queue:
        (in_degree, _), node = queue.pop()
        if in_degree == 0:
            yield node
            # Since we handled the parent, we essentially removed it from the graph
            # decrementing the in-degree of its children by one.
            # To make it be depth first, we make it "win" all ties, among currently existing entries.
            for child in sorted(
                dag.successors(node),
                key=lambda child: score_children(node, child),
            ):
                in_degree, _ = queue[child]
                queue[child] = (in_degree - 1, -counter)
        else:
            msg = f"Cycle exists and includes {node}"
            raise RuntimeError(msg)
        counter += 1


@charmonium.time_block.decor(print_start=True)
def combine_twin_nodes(
    graph: nx.DiGraph[_Node],
    combinable: typing.Callable[[_Node], bool],
) -> nx.DiGraph[frozenset[_Node]]:
    """
    Condensation, replacing combinable twins with a single node.

    - All nodes satisfying the combinable predicate will be replaced with a
      `frozenset[_Node]`. All "twin" nodes, that is nodes with the same
      in-neighbors and out-neighbors, will be combined into one frozenset.

    - Those not satisfying will remain a `_Node`, unchanged.

    Edges will be preserved according to the node mapping.

    """
    neighbors_to_node = dict[tuple[frozenset[_Node], frozenset[_Node]], list[_Node]]()
    non_combinable_nodes = []
    for node in graph.nodes():
        if combinable(node):
            preds = frozenset(graph.predecessors(node))
            succs = frozenset(graph.successors(node))
            neighbors_to_node.setdefault((preds, succs), []).append(node)
        else:
            non_combinable_nodes.append(node)

    mapper = {
        **{node: frozenset(nodes) for nodes in neighbors_to_node.values() for node in nodes},
        **{node: frozenset({node}) for node in non_combinable_nodes},
    }

    return typing.cast(
        "nx.DiGraph[frozenset[_Node]]",
        nx.relabel_nodes(graph, mapper),
    )


def retain_nodes_in_dag(
    dag: nx.DiGraph[_Node],
    retained_nodes: frozenset[_Node],
    edge_data: typing.Callable[[nx.DiGraph[_Node], typing.Sequence[_Node]], EdgeData],
) -> nx.DiGraph[_Node]:
    """
    Return a graph with only the retained nodes.

    - if A and B are retained and connected by a path of non-retained nodes in the input,
      then there is an edge from A to B in the output, whose edge data is edge_data(dag, path_from_A_to_B).
    - and no other edges

    O(nodes + edges)
    """
    assert nx.is_directed_acyclic_graph(dag)
    assert retained_nodes <= set(dag.nodes())

    # Node -> list of pairs of (path to latest retained predecessor, latest retained predecessor)
    # Note that there can be multiple "latest" due to partial ordering.
    # Note that could be itself (not truly a predecessor), but it simplifies the logic.
    latest_retained_predecessors: dict[
        _Node,
        typing.Sequence[tuple[typing.Sequence[_Node], _Node]],
    ] = {}
    earliest_retained_successors: dict[
        _Node,
        typing.Sequence[tuple[typing.Sequence[_Node], _Node]],
    ] = {}

    for node in nx.topological_sort(dag):
        if node in retained_nodes:
            latest_retained_predecessors[node] = (((), node),)
        else:
            latest_retained_predecessors[node] = tuple(
                ((*path_to_retained_predecessor, node), retained_predecessor)
                for predecessor in dag.predecessors(node)
                for path_to_retained_predecessor, retained_predecessor in latest_retained_predecessors[
                    predecessor
                ]
            )

    for node in reversed(list(nx.topological_sort(dag))):
        if node in retained_nodes:
            # path always ends in a retained node
            earliest_retained_successors[node] = (((), node),)
        else:
            # path always ends in a retained node
            earliest_retained_successors[node] = tuple(
                ((node, *path_to_retained_successor), retained_successor)
                for successor in dag.successors(node)
                for path_to_retained_successor, retained_successor in earliest_retained_successors[
                    successor
                ]
            )

    new_graph: nx.DiGraph[_Node] = nx.DiGraph()
    for node, node_data in dag.nodes(data=True):
        if node in retained_nodes:
            # Need to add node directly, in case node is disconnected from everyone
            new_graph.add_node(node, **node_data)

            # Now add edges to retained predecessors/successors
            for predecessor in dag.predecessors(node):
                for path, retained_predecessor in latest_retained_predecessors[predecessor]:
                    assert not any(node in retained_nodes for node in path)
                    assert retained_predecessor in retained_nodes
                    new_path = (retained_predecessor, *path, node)
                    assert nx.is_path(dag, new_path)
                    new_graph.add_edge(retained_predecessor, node, **edge_data(dag, new_path))

            for successor in dag.successors(node):
                for path, retained_successor in earliest_retained_successors[successor]:
                    assert not any(node in retained_nodes for node in path)
                    assert retained_successor in retained_nodes
                    new_path = (node, *path, retained_successor)
                    assert nx.is_path(dag, new_path)
                    new_graph.add_edge(node, retained_successor, **edge_data(dag, new_path))

    assert set(new_graph.nodes()) == retained_nodes

    return new_graph


def create_digraph(
    nodes: It[_Node | tuple[_Node, dict[str, typing.Any]]],
    edges: It[tuple[_Node, _Node] | tuple[_Node, _Node, dict[str, typing.Any]]],
) -> nx.DiGraph[_Node]:
    output: nx.DiGraph[_Node] = nx.DiGraph()
    for node in nodes:
        if isinstance(node, tuple):
            if (
                len(node) == 2
                and isinstance(node[1], dict)
                and all(isinstance(key, str) for key in node[1])
            ):
                output.add_node(node[0], **node[1])
            else:
                raise TypeError(node)
        else:
            output.add_node(node)
    for edge in edges:
        if (
            isinstance(edge, tuple)
            and len(edge) == 3
            and isinstance(edge[2], dict)
            and all(isinstance(key, str) for key in edge[2])
        ):
            output.add_edge(edge[0], edge[1], **edge[2])
        else:
            output.add_edge(edge[0], edge[1])
    return output


def would_create_cycle(
    dag: nx.DiGraph[_Node],
    src: _Node,
    dst: _Node,
) -> bool:
    return any(desc == src for desc in nx.descendants(dag, dst))


def remove_self_edges(
    graph: nx.DiGraph[_Node],
) -> nx.DiGraph[_Node]:
    for src, dst in list(graph.edges()):
        if src == dst:
            graph.remove_edge(src, dst)
    return graph


_Priority = typing.TypeVar("_Priority", bound=util.Comparable)


def topo_sort_with_cycles(
    graph: nx.DiGraph[_Node],
    key: typing.Callable[[_Node], _Priority],
) -> collections.abc.Iterator[_Node]:
    """
    Yield nodes in topological order if possible.

    If cycles exist, arbitrarily choose one node from a cycle
    to continue processing.
    """
    # Compute indegrees
    indegree = dict.fromkeys(graph.nodes, 0)

    for node in graph.nodes:
        for succ in graph.successors(node):
            indegree[succ] += 1

    # Start with all zero-indegree nodes
    queue = collections.deque(node for node, deg in indegree.items() if deg == 0)

    processed = set[_Node]()

    while len(processed) < len(indegree):
        # If no valid node exists, break a cycle arbitrarily
        if not queue:
            arbitrary_choice = next(
                node
                # Try nodes with the lower in-degrees first
                # Ties broken by key
                for node, _ in sorted(
                    indegree.items(),
                    key=lambda pair: (pair[1], key(pair[0])),
                )
                if node not in processed
            )
            queue.append(arbitrary_choice)

        node = queue.popleft()
        yield node
        processed.add(node)

        for succ in graph.successors(node):
            indegree[succ] -= 1
            if indegree[succ] == 0:
                queue.append(succ)


def get_almost_topological_sort(dag: nx.DiGraph[_Node]) -> list[_Node]:
    dag = dag.copy()
    dag.remove_edges_from(nx.selfloop_edges(dag))
    while True:
        basis = list(nx.simple_cycles(dag))
        if not basis:
            return list(nx.topological_sort(dag))
        edges = collections.Counter[tuple[_Node, _Node]]()
        for cycle in basis:
            for edge in [*itertools.pairwise(cycle), (cycle[-1], cycle[0])]:
                edges[edge] += 1
        (source, dest), _ = edges.most_common(1)[0]
        dag.remove_edge(source, dest)
