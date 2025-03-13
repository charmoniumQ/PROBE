import os
import typing
from ..digraph import DiGraph


_Node = typing.TypeVar("_Node")


def to_pydot(graph: DiGraph[_Node]) -> _PyDot: ...


class _PyDot:
    def write_raw(self, f: os.PathLike[str]) -> None: ...
    def write_png(self, f: os.PathLike[str]) -> None: ...
