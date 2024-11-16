import typing
from ...networkx import DiGraph


_Node = typing.TypeVar("_Node")


def to_pydot(graph: DiGraph[_Node]) -> str: ...
