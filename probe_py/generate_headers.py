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
            "--target-python-version=3.12", # "|"-unions and type alias
            "--capitalize-enum-members",
            "--use-generic-container-types", # Sequence instead of list
            # "--collapse-root-models",
            # "--enable-faux-immutability",
            # "--strict-types", "str", "bytes", "int", "float", "bool",
            # "--use-annotated",
            # "--type-mappings", "CString=bytes",
            # "--custom-formatters", "ruff",
        ],
        check=True,
    )


def fixup_autogen_ast(headers_py: pathlib.Path) -> None:
    module = ast.parse(headers_py.read_text())
    add_op_data_property(module)
    remove_unset(module)
    add_immutable(module)
    add_tags(module)
    replace_bytestring_sequence(module)
    fixup_imports(module)
    headers_py.write_text(ast.unparse(module))


def add_op_data_property(module: ast.mod) -> None:
    op_class = find_class(module, "Op")
    op_data_content_variants = []
    for op_data_class in find_classes(module, re.compile(r"OpData\d+")):
        content_field = find_field(op_data_class, "content")
        if isinstance(content_field.annotation, ast.Name):
            op_data_content_variants.append(content_field.annotation.id)
    data_property = ast.parse(f"""
@property
def data(self) -> {" | ".join(op_data_content_variants)}:
    return self.data_tagged.content
    """)
    op_class.body.append(data_property.body[0])


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
    for class_def in find_classes(module, re.compile(r".+")):
        is_struct = any(
            isinstance(base, ast.Name) and base.id == "Struct"
            for base in class_def.bases
        )
        if is_struct:
            class_def.keywords.append(ast.keyword(arg="frozen", value=ast.Constant(value=True)))
            # class_def.keywords.append(ast.keyword(arg="array_like", value=ast.Constant(value=True)))


def add_tags(module: ast.Module) -> None:
    for class_def in [
            *find_classes(module, re.compile(r"OpData\d+")),
            *find_classes(module, re.compile(r"MetadataValue\d+")),
    ]:
        class_def.keywords.append(ast.keyword(arg="tag_field", value=ast.Constant(value="type")))
        type_field = find_field(class_def, "type")
        assert isinstance(type_field.annotation, ast.Subscript)
        tag = type_field.annotation.slice
        assert isinstance(tag, ast.Constant)
        class_def.keywords.append(ast.keyword(arg="tag", value=tag))
        class_def.body = [
            statement
            for statement in class_def.body
            if statement != type_field
        ]


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
                statement.names = [
                    alias
                    for alias in statement.names
                    if alias.name not in {"UNSET", "UnsetType", "Literal"}
                ]


def insert_after_imports(
        module: ast.Module,
        statements: list[ast.stmt],
) -> None:
    last_import = 0
    for i, stmt in enumerate(module.body):
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            last_import = i
    module.body[last_import + 1 : last_import + 1] = statements


def find_classes(module: ast.mod, name: str | re.Pattern[str]) -> collections.abc.Iterator[ast.ClassDef]:
    if isinstance(module, (ast.Module, ast.Interactive)):
        for statement in module.body:
            if isinstance(statement, ast.ClassDef):
                if (isinstance(name, str) and statement.name == name) or \
                   (isinstance(name, re.Pattern) and name.match(statement.name)):
                    yield statement


def find_class(module: ast.mod, name: str) -> ast.ClassDef:
    for class_def in find_classes(module, name):
        return class_def
    raise KeyError(f"class {name} not found in module")


def find_field(class_def: ast.ClassDef, name: str) -> ast.AnnAssign:
    for statement in class_def.body:
        if isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name):
                if statement.target.id == name:
                    return statement
    raise KeyError(f"field {name} not found in class {class_def.name}")


def find_method(class_def: ast.ClassDef, name: str) -> ast.FunctionDef:
    for statement in class_def.body:
        if isinstance(statement, ast.FunctionDef):
            if statement.name == name:
                return statement
    raise KeyError(f"field {name} not found in class {class_def.name}")


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
        haystack: ast.stmt | ast.expr,
        needle: ast.expr,
        substitute: ast.expr,
) -> ast.stmt | ast.expr | str | list[typing.Any]:
    match haystack:
        case None | int():
            return haystack
        case str():
            if isinstance(needle, ast.Name) and isinstance(substitute, ast.Name) and haystack == needle.id:
                print(needle.id, "->", substitute.id)
                return substitute.id
            else:
                return haystack
        case list():
            return [
                replace(elem, needle, substitute)
                for elem in haystack
            ]
        case ast.AST():
            # use ast.compare in Python >= 3.14
            if ast.unparse(haystack) == ast.unparse(needle):
                print("repl", ast.unparse(haystack), "->", ast.unparse(substitute))
                return substitute
            else:
                ret = type(haystack)(**{
                    keyword: replace(value, needle, substitute)
                    for keyword, value in haystack.__dict__.items() 
                })
                return ret


if __name__ == "__main__":
    main()
