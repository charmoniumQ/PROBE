from __future__ import annotations
import abc
import dataclasses
from collections.abc import Iterable as It, Sequence as Seq, Mapping as Map
import itertools
import typing
import charmonium.time_block
from . import graph_utils
import networkx


_Node = typing.TypeVar("_Node")


# Makes it slow, but assert more invariants
DEBUG_ASSERTIONS: typing.Final[bool] = False


class PartialOrder(abc.ABC, typing.Generic[_Node]):
    @abc.abstractmethod
    def leq(self, node0: _Node, node1: _Node) -> bool:
        ...

    def is_antichain(self, nodes: It[_Node]) -> bool:
        return all(
            not self.leq(node0, node1)
            for node0, node1 in itertools.combinations(nodes, 2)
        )

    def is_peer(self, u: _Node, v: _Node) -> bool:
        return not self.leq(u, v) and not self.leq(v, u)

    def sorted(self, nodes: It[_Node]) -> Seq[_Node]:
        dag: networkx.DiGraph[_Node] = networkx.DiGraph()
        dag.add_nodes_from(nodes)
        dag.add_edges_from([
            (source, target)
            for source in nodes
            for target in nodes
            if self.leq(source, target)
            and source != target
        ])
        assert networkx.is_directed_acyclic_graph(dag)
        if DEBUG_ASSERTIONS:
            pass
        return list(networkx.topological_sort(dag))

    def upper_bounds(self, nodes: It[_Node]) -> frozenset[_Node]:
        uppermost_nodes = set[_Node]()
        covered_nodes = set[_Node]()
        sorted_nodes = self.sorted(nodes)
        for i, candidate in enumerate(sorted_nodes):
            if candidate not in covered_nodes:
                uppermost_nodes.add(candidate)
                covered_nodes.update(
                    descendant
                    for descendant in sorted_nodes[i+1:]
                    if self.leq(candidate, descendant)
                )
        if DEBUG_ASSERTIONS:
            assert all(
                any(
                    uppermost_node == node or self.leq(uppermost_node, node)
                    for uppermost_node in uppermost_nodes)
                for node in nodes
            )
            assert not any(
                self.leq(a, b)
                for a in uppermost_nodes
                for b in uppermost_nodes
                if a != b
            )
        return frozenset(uppermost_nodes)

    def lower_bounds(self, nodes: It[_Node]) -> frozenset[_Node]:
        bottom_nodes = set[_Node]()
        covered_nodes = set[_Node]()
        sorted_nodes = self.sorted(nodes)[::-1]
        for i, candidate in enumerate(sorted_nodes):
            if candidate not in covered_nodes:
                bottom_nodes.add(candidate)
                covered_nodes.update(
                    ancestor
                    for ancestor in sorted_nodes[i+1:]
                    if self.leq(ancestor, candidate)
                )
        if DEBUG_ASSERTIONS:
            assert all(
                any(
                    bottom_node == node or self.leq(node, bottom_node)
                    for bottom_node in bottom_nodes
                )
                for node in nodes
            )
            assert not any(
                self.leq(a, b)
                for a in bottom_nodes
                for b in bottom_nodes
                if a != b
            )
        return frozenset(bottom_nodes)

    def non_ancestors(
            self,
            candidates: It[_Node],
            lower_bounds: It[_Node],
    ) -> It[_Node]:
        "Return all candidates that are not ancestors of any element in lower_bounds."
        return frozenset({
            candidate
            for candidate in candidates
            if not any(
                    self.leq(candidate, lower_bound)
                    for lower_bound in lower_bounds
            )
        })

    def non_descendants(
            self,
            candidates: It[_Node],
            upper_bounds: It[_Node],
    ) -> It[_Node]:
        "Return all candidates that are not descendent of any element in upper_bounds."
        return frozenset({
            candidate
            for candidate in candidates
            if not any(
                    self.leq(upper_bound, candidate)
                    for upper_bound in upper_bounds
            )
        })

    def interval(self, upper_bound: It[_Node], lower_bound: It[_Node]) -> Interval[_Node]:
        return Interval(self, frozenset(upper_bound), frozenset(lower_bound))

    def singleton(self, node: _Node) -> Interval[_Node]:
        return Interval(self, frozenset({node}), frozenset({node}))

    def hasse_diagram(self, nodes: It[_Node]) -> networkx.DiGraph[_Node]:
        ret: networkx.DiGraph[_Node] = networkx.DiGraph()
        for node in nodes:
            ret.add_node(node)
        for node0, node1 in itertools.permutations(nodes, r=2):
            if self.leq(node0, node1):
                ret.add_edge(node0, node1)
        return networkx.transitive_reduction(ret)

    def interval_order(self) -> IntervalOrder[_Node]:
        return IntervalOrder(self)

    def reverse(self) -> ReversedOrder[_Node]:
        return ReversedOrder(self)


@dataclasses.dataclass(frozen=True)
class ReversedOrder(PartialOrder[_Node]):
    order: PartialOrder[_Node]
    def leq(self, a: _Node, b: _Node) -> bool:
        return self.order.leq(b, a)


@dataclasses.dataclass(frozen=True)
class Interval(typing.Generic[_Node]):
    leq: PartialOrder[_Node]
    upper_bound: frozenset[_Node]
    lower_bound: frozenset[_Node]

    def __hash__(self) -> int:
        return hash(self.upper_bound) ^ hash(self.lower_bound)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Interval) and self.upper_bound == other.upper_bound and self.lower_bound == other.lower_bound

    def __post_init__(self) -> None:
        if DEBUG_ASSERTIONS:
            assert self.leq.is_antichain(self.upper_bound), \
                f"{self.upper_bound} is not an antichain"
            assert self.leq.is_antichain(self.lower_bound), \
                f"{self.lower_bound} is not an antichain"

    def __bool__(self) -> bool:
        "Whether the interval is non-empty"
        return bool(self.upper_bound)

    def __lt__(self, other: Interval[_Node]) -> bool:
        if other.leq is not self.leq:
            raise ValueError("Cannot compare intervals of different orders")
        else:
            return self.all_less_than(other)

    @staticmethod
    def union(*intervals: Interval[_Node]) -> Interval[_Node]:
        leq = intervals[0].leq
        if DEBUG_ASSERTIONS:
            assert all(interval.leq is leq for interval in intervals)
        upper_bound = leq.upper_bounds(frozenset(
            node
            for interval in intervals
            for node in interval.upper_bound
        ))
        lower_bound = leq.lower_bounds(frozenset(
            node
            for interval in intervals
            for node in interval.lower_bound
        ))
        return Interval(leq, frozenset(upper_bound), frozenset(lower_bound))

    def all_less_than(self, other: Interval[_Node]) -> bool:
        other_upper_bounds_that_are_not_descendent_of_self_lower_bounds = \
            self.leq.non_descendants(other.upper_bound, self.lower_bound)
        return not other_upper_bounds_that_are_not_descendent_of_self_lower_bounds


@dataclasses.dataclass(frozen=True)
class IntervalOrder(typing.Generic[_Node], PartialOrder[Interval[_Node]]):
    node_order: PartialOrder[_Node]
    def leq(self, interval0: Interval[_Node], interval1: Interval[_Node]) -> bool:
        return interval0.all_less_than(interval1)


@charmonium.time_block.decor(print_start=False)
def peers(
        order: PartialOrder[_Node],
        dag: networkx.DiGraph[_Node],
) -> Map[_Node, Interval[_Node]]:
    my_highest_peers = highest_peers(order, dag)
    my_lowest_peers = highest_peers(order.reverse(), dag.reverse())
    return {
        node: order.interval(my_highest_peers[node], my_lowest_peers[node])
        for node in dag.nodes()
    }


def highest_peers(
        order: PartialOrder[_Node],
        dag: networkx.DiGraph[_Node],
) -> Map[_Node, frozenset[_Node]]:
    if DEBUG_ASSERTIONS:
        assert networkx.is_directed_acyclic_graph(dag)
    highest_peers = {node: set[_Node]() for node in dag.nodes()}

    sources = graph_utils.get_sources(dag)
    for source0, source1 in itertools.permutations(sources, 2):
        highest_peers[source0].add(source1)

    for node in networkx.topological_sort(dag):
        highest_peers_of_parent = set[_Node]()
        siblings = set[_Node]()
        for parent in dag.predecessors(node):
            highest_peers_of_parent.update(highest_peers[parent])
            for sibling in dag.successors(parent):
                if sibling != node:
                    siblings.add(sibling)
        if DEBUG_ASSERTIONS:
            for peer_of_parent in highest_peers_of_parent:
                # Peer of my parent either points to me or is my peer, but I don't point to them.
                assert not order.leq(node, peer_of_parent)
        highest_peers_of_parent_and_me = {
            highest_peer_of_parent
            for highest_peer_of_parent in highest_peers_of_parent
            if not order.leq(highest_peer_of_parent, node)
        }
        siblings_that_are_highest_peers = {
            sibling
            for sibling in siblings
            if not order.leq(sibling, node) and not order.leq(node, sibling) and not any(order.leq(highest_peer_of_parent_and_me, sibling) for highest_peer_of_parent_and_me in highest_peers_of_parent_and_me)
        }
        highest_peers[node] = highest_peers_of_parent_and_me | siblings_that_are_highest_peers 
        if DEBUG_ASSERTIONS:
            assert order.is_antichain(highest_peers[node])
            highest_peer_groups = {"highest peers of parent and me": highest_peers_of_parent_and_me, "siblings that are peers": siblings_that_are_highest_peers}
            for label, highest_peer_group in highest_peer_groups.items():
                for highest_peer in highest_peer_group:
                    for parent_of_highest_peer in dag.predecessors(highest_peer):
                        assert order.leq(parent_of_highest_peer, node), (label, node, highest_peer, parent_of_highest_peer)

    return {node: frozenset(peers) for node, peers in highest_peers.items()}


def topo_sort_subset(
        order: PartialOrder[_Node],
        dag: networkx.DiGraph[_Node],
        upper_bound: It[_Node],
        lower_bound: It[_Node],
) -> typing.Generator[_Node | None, bool | None, None]:
    """Antichain traversal with pruning

    Antichain traversal means that nodes will be iterated in order starting from upper_bound.

    Edges that reach outside of upper bound don't matter, but edges that terminate in an upper_bound are respected.

    Searching stops at lower_bound, or if the branch has been pruned.

    Note that if a branch has been pruned, its successors may stll be iterated over, if the graph is shaped like a Y.

    A -> B <- C, where we prune A, but C is still iterated, and therefore B is still iterated.

        traversal = bfs_with_pruning
        for node in traversal:
            assert node is not None
            # work on node
            traversal.send(condition) # send True to descend or False to prune

    """
    if DEBUG_ASSERTIONS:
        assert order.is_antichain(upper_bound)
        assert order.is_antichain(lower_bound)
    frontier = list(upper_bound)
    next_frontier = set[_Node]()
    while frontier:
        node = frontier.pop()
        continue_with_children = yield node
        should_be_none = yield None
        assert should_be_none is None
        if continue_with_children:
            next_frontier.update(
                successor
                for successor in dag.successors(node)
                if successor in lower_bound or not any(order.leq(lb, successor) for lb in lower_bound)
            )
        if not frontier:
            frontier = list(order.upper_bounds(next_frontier))
            next_frontier -= set(frontier)
    assert not next_frontier
