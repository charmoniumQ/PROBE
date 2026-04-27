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
            # "--collapse-root-models", # copy Union types at every use-site, rather than definint it once
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
    remove_unset(module)
    add_immutable(module)
    fix_tagged_enums(module)
    replace_bytestring_sequence(module)
    fixup_imports(module)
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
    classes_to_replace: dict[str, str] = {}
    for class_def in module.body[:]:
        if isinstance(class_def, ast.ClassDef):
            try:
                type_field = find_field(class_def, "type")
            except KeyError:
                pass
            else:
                assert isinstance(type_field, ast.AnnAssign)
                assert isinstance(type_field.annotation, ast.Subscript)
                assert isinstance(type_field.annotation.value, ast.Name)
                assert type_field.annotation.value.id == "Literal"
                assert isinstance(type_field.annotation.slice, ast.Constant)
                assert isinstance(type_field.annotation.slice.value, str)
                tag_value = type_field.annotation.slice.value
                find_class(module, tag_value) # assert class with this tag exists
                classes_to_replace[class_def.name] = tag_value
                module.body.remove(class_def)

    for old_class, new_class in classes_to_replace.items():
        module.body = [
            replace(stmt, ast.Name(id=old_class), ast.Name(id=new_class))
            for stmt in module.body
        ]
        new_class_def = find_class(module, new_class)
        new_class_def.keywords.append(ast.keyword(arg="tag", value=ast.Constant(value=True)))


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


def add_typedefs(module: ast.mod) -> None:
    if isinstance(module, (ast.Module, ast.Interactive)):
        module.body = module.body + [
            ast.AnnAssign(
                target=ast.Name(id='AT_FDCWD'),
                annotation=ast.Subscript(
                    value=ast.Name(id="Final"),
                    slice=ast.Name(id="OpenNumber"),
                ),
                value=ast.Call(
                    func=ast.Name(id="OpenNumber"),
                    args=[ast.Constant(value=-100)],
                    keywords=[],
                ),
                simple=True,
            ),
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


def find_classes(
        module: ast.mod,
        name: str | re.Pattern[str] = re.compile(r".+"),
) -> collections.abc.Iterator[ast.ClassDef]:
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
