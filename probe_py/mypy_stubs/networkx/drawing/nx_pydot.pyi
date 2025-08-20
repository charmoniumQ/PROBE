import typing
from .. import DiGraph
import pydot


_Node = typing.TypeVar("_Node")


def to_pydot(graph: DiGraph[_Node]) -> pydot.Dot: ...
