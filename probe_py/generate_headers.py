#!/usr/bin/env python

import ast
import collections
import os
import pathlib
import re
import subprocess
import typing


def main() -> None:
    headers_py = pathlib.Path(os.environ["PYTHON_HEADER_OUTFILE"])
    jsonschema = pathlib.Path(os.environ["JSONSCHEMA_OUTFILE"])
    autogen_code(jsonschema, headers_py)
    fixup_autogen_ast(headers_py)


def autogen_code(jsonschema: pathlib.Path, headers_py: pathlib.Path) -> None:
    subprocess.run(
        [
            "datamodel-codegen",
            "--input", str(jsonschema),
            "--input-file-type=jsonschema",
            "--output-model-type=msgspec.Struct",
            "--output",
            str(headers_py),

            # "|"-unions and type alias
            "--target-python-version=3.13",

            "--capitalize-enum-members",

            # Sequence[_T] instead of list[_T]
            "--use-generic-container-types",

            # copy Union types at every use-site, rather than defining it once
            # that creates a lot of code duplication
            # "--collapse-root-models",

            # faux immutability only seems to work for Pydantic models.
            # Instead, we will use `add_immutable`
            # "--enable-faux-immutability",

            # Code already uses annotated.
            # This might be only for pydantic
            "--use-annotated",

            # Without this, we get:
            #
            #     UserWarning: format of 'uint16' not understood for 'integer' - using default
            #
            "--type-mappings", "integer+uint8=integer", "integer+uint16=integer", "integer+uint32=integer", "integer+uint64=integer",

            # Without this, we get,
            #
            #     FutureWarning: The default external formatters (black, isort) will become opt-in in a future version.
            #     To keep the current behavior, specify formatters=[Formatter.BLACK, Formatter.ISORT].
            #     To prepare for dependency-free formatting, use formatters=[Formatter.BUILTIN].
            #     To suppress this warning, specify formatters explicitly."
            #
            "--formatters",
            "ruff-check",
            "ruff-format",
        ],
        check=True,
    )


def fixup_autogen_ast(headers_py: pathlib.Path) -> None:
    module = ast.parse(headers_py.read_text())
    remove_unset(module)
    add_immutable(module)
    # fix_tagged_enums(module)
    replace_bytestring_sequence(module)
    fixup_imports(module)
    add_properties(module)
    add_typedefs(module)
    headers_py.write_text(ast.unparse(module))


def remove_unset(module: ast.Module) -> None:
    unset = ast.parse("UNSET", mode="eval").body
    unset_type = ast.parse("UnsetType", mode="eval").body
    none = ast.parse("None", mode="eval").body
    module.body = [
        replace(replace(stmt, unset, none), unset_type, none)
        if not isinstance(stmt, ast.ImportFrom) else stmt
        for stmt in module.body
        
    ]


def add_immutable(module: ast.Module) -> None:
    for class_def in find_classes(module):
        is_struct = any(
            isinstance(base, ast.Name) and base.id == "Struct"
            for base in class_def.bases
        )
        if is_struct:
            class_def.keywords.append(ast.keyword(arg="frozen", value=ast.Constant(value=True)))
            # class_def.keywords.append(ast.keyword(arg="array_like", value=ast.Constant(value=True)))


def fix_tagged_enums(module: ast.Module) -> None:
    replace_string: dict[str, str] = {}

    for class_def in module.body[:]:
        if isinstance(class_def, ast.ClassDef):
            tag = {
                keyword.arg: keyword.value
                for keyword in class_def.keywords
            }.get("tag")
            if tag:
                assert isinstance(tag, ast.Constant)
                assert isinstance(tag.value, str)
                replace_string[class_def.name] = tag.value
                class_def.name = tag.value


def replace_bytestring_sequence(module: ast.Module) -> None:
    bytes_ast = ast.parse("bytes", mode="eval").body
    module.body = [
        ast.TypeAlias(
            **{
                **stmt.__dict__,
                "value": bytes_ast,
            }
        )
        if isinstance(stmt, ast.TypeAlias) and stmt.name.id in {"FixedPath", "ByteString"}
        else stmt
        for stmt in module.body
    ]
    stringarrayitem_sequence = ast.parse("Sequence[StringArrayItem]", mode="eval").body
    module.body = [
        replace(statement, stringarrayitem_sequence, bytes_ast)
        for statement in module.body
    ]


def fixup_imports(module: ast.mod) -> None:
    if isinstance(module, (ast.Module, ast.Interactive)):
        for statement in module.body:
            if isinstance(statement, ast.ImportFrom):
                if statement.module == "msgspec":
                    statement.names = [
                        alias
                        for alias in statement.names
                        if alias.name not in {"UNSET", "UnsetType"}
                    ]
                elif statement.module == "typing":
                    statement.names = [
                        alias
                        for alias in statement.names
                        if alias.name not in {"Literal",}
                    ] + [ast.alias("Final")]


def add_properties(module: ast.mod) -> None:
    open_number_class = find_class(module, "OpenNumber")
    open_number_class.body.extend(ast.parse("""

@property
def number(self) -> int:
    return self.raw_number & 0x3FFF

@property
def is_read(self) -> bool:
    return bool(self.raw_number & 0x4000)

@property
def is_write(self) -> bool:
    return bool(self.raw_number & 0x8000)

def __str__(self) -> str:
    return f"{self.fd},{self.number}{"R" if self.is_read else ""}{"W" if self.is_write else ""}"
""").body)


def add_typedefs(module: ast.mod) -> None:
    if isinstance(module, (ast.Module, ast.Interactive)):
        module.body = module.body + [
            ast.AnnAssign(
                target=ast.Name(id='AT_FDCWD'),
                annotation=ast.Subscript(
                    value=ast.Name(id="Final"),
                    slice=ast.Name(id="int"),
                ),
                # cpp -E <(echo -e '#include <fcntl.h>\nAT_FDCWD') | tail --lines=1
                value=ast.Constant(value=2**16 - 100),
                simple=True,
            ),
            ast.AnnAssign(
                target=ast.Name(id='O_CLOEXEC'),
                annotation=ast.Subscript(
                    value=ast.Name(id="Final"),
                    slice=ast.Name(id="int"),
                ),
                # cpp -E <(echo -e '#include <fcntl.h>\nO_CLOEXEC') | tail --lines=1
                value=ast.Constant(0o2000000),
                simple=True,
            ),
            ast.AnnAssign(
                target=ast.Name(id='FD_CLOEXEC'),
                annotation=ast.Subscript(
                    value=ast.Name(id="Final"),
                    slice=ast.Name(id="int"),
                ),
                # cpp -E <(echo -e '#include <fcntl.h>\nFD_CLOEXEC') | tail --lines=1
                value=ast.Constant(1),
                simple=True,
            ),
        ]
    else:
        raise TypeError()


def insert_after_imports(
        module: ast.Module,
        statements: list[ast.stmt],
) -> None:
    last_import = 0
    for i, stmt in enumerate(module.body):
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            last_import = i
    module.body[last_import + 1 : last_import + 1] = statements


def find_classes(
        module: ast.mod,
        name: str | re.Pattern[str] = re.compile(r".+"),
) -> collections.abc.Iterator[ast.ClassDef]:
    if isinstance(module, (ast.Module, ast.Interactive)):
        for statement in module.body:
            if (
                    isinstance(statement, ast.ClassDef)
                    and ((isinstance(name, str) and statement.name == name)
                       or (isinstance(name, re.Pattern) and name.match(statement.name)))
            ):
                    yield statement


def find_class(module: ast.mod, name: str) -> ast.ClassDef:
    for class_def in find_classes(module, name):
        return class_def
    raise KeyError(f"class {name} not found in module")


def find_field(class_def: ast.ClassDef, name: str) -> ast.AnnAssign:
    for statement in class_def.body:
        if (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == name
        ):
                    return statement
    raise KeyError(f"field {name} not found in class {class_def.name}")


@typing.overload
def replace(
        haystack: ast.Module,
        needle: ast.expr,
        substitute: ast.expr,
) -> ast.stmt:
    pass
@typing.overload
def replace(
        haystack: ast.stmt,
        needle: ast.expr,
        substitute: ast.expr,
) -> ast.stmt:
    pass
@typing.overload
def replace(
        haystack: ast.expr,
        needle: ast.expr,
        substitute: ast.expr,
) -> ast.expr:
    pass
def replace(
        haystack: ast.Module | ast.stmt | ast.expr,
        needle: ast.expr,
        substitute: ast.expr,
) -> ast.Module | ast.stmt | ast.expr | str | list[typing.Any]:
    match haystack:
        case None | int() | str():
            return haystack
        case list():
            return [
                replace(elem, needle, substitute)
                for elem in haystack
            ]
        case ast.AST():
            # TODO: use ast.compare in Python >= 3.14
            if ast.unparse(haystack) == ast.unparse(needle):
                return substitute
            else:
                return type(haystack)(**{
                    keyword: replace(value, needle, substitute) if keyword != "parent" else value
                    for keyword, value in haystack.__dict__.items()
                })


if __name__ == "__main__":
    main()
