import collections
import typing


_T = typing.TypeVar("_T", bound=typing.Hashable)


class DisjointSets(typing.Generic[_T]):
    def __init__(self, nodes: collections.abc.Iterable[_T]):
        self.parent = {node: node for node in nodes}
        self.rank = {node: 0 for node in self.parent.keys()}

    def find(self, node: _T) -> _T:
        parent = self.parent[node]
        if parent != node:
            self.parent[node] = self.find(parent)  # path compression
        return self.parent[node]

    def union(self, a: _T, b: _T) -> bool:
        root_of_a = self.find(a)
        root_of_b = self.find(b)

        if root_of_a == root_of_b:
            return False

        # union by rank
        if self.rank[root_of_a] < self.rank[root_of_b]:
            root_of_a, root_of_b = root_of_b, root_of_a

        self.parent[root_of_b] = root_of_a

        if self.rank[root_of_a] == self.rank[root_of_b]:
            self.rank[root_of_a] += 1

        return True

    def connected(self, root_of_a: _T, root_of_b: _T) -> bool:
        return self.find(root_of_a) == self.find(root_of_b)

    def sets(self) -> collections.abc.Iterator[set[_T]]:
        groups = collections.defaultdict[_T, set[_T]](set)
        for node in self.parent.keys():
            groups[self.find(node)].add(node)
        return iter(groups.values())
