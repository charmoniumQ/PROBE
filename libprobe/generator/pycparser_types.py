from __future__ import annotations
import typing
import pycparser  # type: ignore
import dataclasses


if typing.TYPE_CHECKING:
    class CGenerator:
        def _parenthesize_if(self, n: Node, condition: typing.Callable[[Node], bool]) -> str: ...
        def _generate_decl(self, n: pycparser.c_ast.Node) -> str: ...
        def visit(self, n: pycparser.c_ast.Node | str | list[str]) -> str: ...
        def _visit_expr(self, n: pycparser.c_ast.Node) -> str: ...
        def _make_indent(self) -> str: ...
        indent_level: int
    class Node:
        def __iter__(self) -> typing.Iterator[Node]: ...
    @dataclasses.dataclass
    class IdentifierType(Node):
        names: list[str]
    @dataclasses.dataclass
    class Assignment(Node):
        op: str
        lvalue: Node
        rvalue: Node
    @dataclasses.dataclass
    class Compound(Node):
        block_items: list[Node]
    @dataclasses.dataclass
    class ID(Node):
        name: str
    @dataclasses.dataclass
    class Decl(Node):
        name: str
        quals: list[str]
        align: list[str]
        storage: list[str]
        funcspec: list[str]
        type: TypeDecl | PtrDecl
        init: Node | None = None
        bitsize: Node | None = None
    @dataclasses.dataclass
    class TypeDecl(Node):
        declname: str | None
        quals: list[Node]
        align: Node | None
        type: Node
    @dataclasses.dataclass
    class FuncDecl(Node):
        args: ParamList | None
        type: TypeDecl
    @dataclasses.dataclass
    class ParamList(Node):
        params: list[Decl]
    @dataclasses.dataclass
    class PtrDecl(Node):
        quals: list[str]
        type: TypeDecl | FuncDecl
else:
    CGenerator = pycparser.c_generator.CGenerator
    Node = pycparser.c_ast.Node
    IdentifierType = pycparser.c_ast.IdentifierType
    Assignment = pycparser.c_ast.Assignment
    Compound = pycparser.c_ast.Compound
    Decl = pycparser.c_ast.Decl
    TypeDecl = pycparser.c_ast.TypeDecl
    ID = pycparser.c_ast.ID
    FuncDecl = pycparser.c_ast.FuncDecl
    ParamList = pycparser.c_ast.ParamList
    PtrDecl = pycparser.c_ast.PtrDecl


