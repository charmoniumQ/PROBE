import typing


_T = typing.TypeVar("_T")


class DisjointSet(typing.Generic[_T]):
    def __init__(self, elems: typing.Iterable[_T]) -> None: ...
    def merge(self, i0: _T, i1: _T) -> bool: ...
    def subsets(self) -> typing.Sequence[frozenset[_T]]: ...
