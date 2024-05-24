import ctypes
import dataclasses
import enum
import pathlib
import random
import typing
import pycparser # type: ignore


_T = typing.TypeVar("_T")


CType = type[ctypes.Structure] | type[ctypes.Union] | type[ctypes._SimpleCData]
CTypeMap = typing.Mapping[tuple[str, ...], CType | Exception]
CTypeDict = dict[tuple[str, ...], CType | Exception]
default_c_types: CTypeMap = {
    ("_Bool",): ctypes.c_bool,
    ("char",): ctypes.c_char,
    ("wchar_t",): ctypes.c_wchar,
    ("unsigned", "char"): ctypes.c_ubyte,
    ("short",): ctypes.c_short,
    ("unsigned", "short"): ctypes.c_ushort,
    (): ctypes.c_int,
    ("unsigned",): ctypes.c_uint,
    ("long",): ctypes.c_long,
    ("unsigned", "long"): ctypes.c_ulong,
    ("long", "long"): ctypes.c_longlong,
    ("__int64",): ctypes.c_longlong,
    ("unsigned", "long", "long"): ctypes.c_ulonglong,
    ("unsigned", "__int64"): ctypes.c_ulonglong,
    ("size_t",): ctypes.c_size_t,
    ("ssize_t",): ctypes.c_ssize_t,
    ("time_t",): ctypes.c_time_t, # type: ignore
    ("float",): ctypes.c_float,
    ("double",): ctypes.c_double,
    ("long", "double",): ctypes.c_longdouble,
    ("char*",): ctypes.c_char_p,
    ("wchar_t*",): ctypes.c_wchar_p,
    ("void*",): ctypes.c_void_p,
}


class PyStructBase:
    pass


class PyUnionBase:
    pass


PyType = type[bool] | type[int] | type[float] | type[str] | enum.EnumType | type[PyStructBase] | type[PyUnionBase] | type[object]
PyTypeMap = typing.Mapping[tuple[str, ...], PyType | Exception]
PyTypeDict = dict[tuple[str, ...], PyType | Exception]
default_py_types: PyTypeMap = {
    ("_Bool",): bool,
    ("char",): str,
    ("wchar_t",): str,
    ("unsigned", "char"): int,
    ("short",): int,
    ("unsigned", "short"): int,
    (): int,
    ("unsigned",): int,
    ("long",): int,
    ("unsigned", "long"): int,
    ("long", "long"): int,
    ("__int64",): int,
    ("unsigned", "long", "long"): int,
    ("unsigned", "__int64"): int,
    ("size_t",): int,
    ("ssize_t",): int,
    ("time_t",): int, # type: ignore
    ("float",): float,
    ("double",): float,
    ("long", "double",): int,
    ("char*",): str,
    ("wchar_t*",): str,
    ("void*",): int,
}
assert default_py_types.keys() == default_c_types.keys()


def _expect_type(typ: type[_T], val: typing.Any) -> _T:
    if isinstance(val, typ):
        return val
    else:
        raise TypeError(f"Expected value of type {typ}, but got {val} of type {type(val)}")


def _normalize_name(name: tuple[str, ...]) -> tuple[str, ...]:
    # Move 'unsigned' to the beginning (if exists)
    # Delete 'signed' (default is assume signed; signed short == short)
    # Delete 'int' (default is assume int; unsigned int == unsigned)
    return (
        *(("unsigned",) if "unsigned" in name else ()),
        *(t for t in name if t not in {"signed", "int", "unsigned"}),
    )


for type_name in default_c_types.keys():
    assert _normalize_name(type_name) == type_name


def _lookup_type(
        c_types: CTypeDict,
        py_types: PyTypeDict,
        type_name: tuple[str, ...],
) -> tuple[CType | Exception, PyType | Exception]:
    if len(type_name) > 1 and type_name[1] is None:
        raise TypeError
    c_type = c_types.get(type_name, KeyError(f"{type_name} not found"))
    if isinstance(c_type, Exception):
        c_type = NotImplementedError(f"Can't parse {type_name} due to {c_type!s}")
    py_type = py_types.get(type_name, KeyError)
    if isinstance(py_type, Exception):
        py_type = object
    return c_type, py_type


def eval_compile_time_int(c_types, py_types, typ: pycparser.c_ast.Node, name: str) -> int | Exception:
    if False:
        pass
    elif isinstance(typ, pycparser.c_ast.Constant):
        if typ.type == "int":
            return int(typ.value)
        else:
            raise TypeError(f"{typ}")
    elif isinstance(typ, pycparser.c_ast.UnaryOp):
        if typ.op == "sizeof":
            c_type, _ = ast_to_cpy_type(c_types, py_types, typ.expr.type, None)
            if isinstance(c_type, Exception):
                return c_type
            else:
                return ctypes.sizeof(c_type)
        else:
            return eval(f"{typ.op} {eval_compile_time_int(c_types, py_types, typ.expr, name)}")
    elif isinstance(typ, pycparser.c_ast.BinaryOp):
        left = eval_compile_time_int(c_types, py_types, typ.left, name + "_left")
        right = eval_compile_time_int(c_types, py_types, typ.right, name + "_right")
        return int(eval(f"{left} {typ.op} {right}"))
    elif isinstance(typ, pycparser.c_ast.Cast):
        return eval_compile_time_int(c_types, py_types, typ.expr, name)
    raise TypeError(f"{typ}")


def ast_to_cpy_type(
        c_types: CTypeDict,
        py_types: PyTypeDict,
        typ: pycparser.c_ast.Node,
        name: str | None,
) -> tuple[CType | Exception, PyType | Exception]:
    """
    c_types and py_types: are the bank of c_types and py_types that have already been parsed, and may be added to while parsing typ.
    typ: is the AST representing the type of a field.
    name: is a prefix that will be used if this is an anonymous struct/union/enum and we have to give it an arbitrary name.
    """

    if False:
        pass
    elif isinstance(typ, pycparser.c_ast.TypeDecl):
        return ast_to_cpy_type(c_types, py_types, typ.type, name)
    elif isinstance(typ, pycparser.c_ast.IdentifierType):
        return _lookup_type(c_types, py_types, _normalize_name(tuple(typ.names)))
    elif isinstance(typ, pycparser.c_ast.PtrDecl):
        return NotImplementedError("Pointers"), NotImplementedError("Pointers")
    elif isinstance(typ, pycparser.c_ast.ArrayDecl):
        repetitions = eval_compile_time_int(c_types, py_types, typ.dim, name)
        inner_c_type, inner_py_type = ast_to_cpy_type(c_types, py_types, typ.type.type, name)
        array_c_type: CType | Exception
        array_py_type: PyType | Exception
        if isinstance(inner_c_type, Exception):
            array_c_type = inner_c_type
        else:
            array_c_type = inner_c_type * repetitions # type: ignore
        if isinstance(inner_py_type, Exception):
            array_py_type = inner_py_type
        else:
            array_py_type = tuple[*([inner_py_type] * repetitions)] # type: ignore
        return array_c_type, array_py_type
    elif isinstance(typ, pycparser.c_ast.Enum):
        if typ.values is None:
            # Reference to already-defined type
            inner_name = typ.name
            assert inner_name is not None
        else:
            # Defining a new enum inline (possibly anonymous)
            inner_name = typ.name
            if inner_name is None:
                inner_name = f"{name}_enum"
            parse_enum(c_types, py_types, typ, inner_name)
        return _lookup_type(c_types, py_types, ("enum", inner_name))
    elif isinstance(typ, (pycparser.c_ast.Struct, pycparser.c_ast.Union)):
        inner_is_struct = isinstance(typ, pycparser.c_ast.Struct)
        inner_keyword = "struct" if inner_is_struct else "union"
        if typ.decls is None:
            # Reference to already-defined type
            inner_name = typ.name
            assert inner_name is not None
        else:
            # Defining a new type inline (possibly anonymous)
            inner_name = typ.name
            if inner_name is None:
                # New type is anonymous; let's make a name and hope for no collisions
                inner_name = f"{name}_{inner_keyword}"
            parse_struct_or_union(c_types, py_types, typ, inner_name)
        return _lookup_type(c_types, py_types, (inner_keyword, inner_name))
    else:
        raise TypeError(f"Don't know how to convert {type(typ)} {typ} to C/python type")


def parse_struct_or_union(
        c_types: CTypeDict,
        py_types: PyTypeDict,
        struct_decl: pycparser.c_ast.Struct | pycparser.c_ast.Union,
        name: str,
) -> None:
    assert isinstance(struct_decl, (pycparser.c_ast.Struct, pycparser.c_ast.Union))
    is_struct = isinstance(struct_decl, pycparser.c_ast.Struct)
    field_names = [decl.name for decl in struct_decl.decls]
    field_c_types = list[CType]()
    field_py_types = list[PyType]()
    c_type_error: Exception | None = None

    for decl in struct_decl.decls:
        c_type, py_type = ast_to_cpy_type(c_types, py_types, decl.type, f"{name}_{decl.name}")
        if isinstance(c_type, Exception):
            c_type_error = c_type
        else:
            field_c_types.append(c_type)
        if isinstance(py_type, Exception):
            py_type_error = py_type
        else:
            field_py_types.append(py_type)

    keyword = "struct" if is_struct else "union"
    py_types[(keyword, name)] = dataclasses.make_dataclass(
        name,
        zip(field_names, field_py_types),
        bases=(PyStructBase,)
    )

    if c_type_error is None:
        c_types[(keyword, name)] = type(
            name,
            (ctypes.Structure if is_struct else ctypes.Union,),
            {"_fields_": list(zip(field_names, field_c_types))},
        )
    else:
        c_types[(keyword, name)] = c_type_error


def parse_enum(
        c_types: CTypeDict,
        py_types: PyTypeDict,
        enum_decl: pycparser.c_ast.Enum,
        name: str,
) -> None:
    assert isinstance(enum_decl, pycparser.c_ast.Enum)
    c_types[("enum", name)] = c_types[("unsigned",)]
    py_enum_fields = list[tuple[str, int]]()
    current_value = 0
    for item in enum_decl.values.enumerators:
        if item.value:
            current_value = item.value
        py_enum_fields.append((item.name, current_value))
        current_value += 1
    py_types[("enum", name)] = typing.cast(
        type[enum.IntEnum],
        enum.IntEnum(name, py_enum_fields),
    )


def parse_typedef(
        c_types: CTypeDict,
        py_types: PyTypeDict,
        typedef: pycparser.c_ast.Typedef,
) -> None:
    c_type, py_type = ast_to_cpy_type(c_types, py_types, typedef.type, typedef.name)
    c_types[(typedef.name,)] = c_type
    py_types[(typedef.name,)] = py_type


def parse_all_types(
        c_types: CTypeDict,
        py_types: PyTypeDict,
        stmts: pycparser.c_ast.Node,
) -> None:
    for stmt in stmts:
        if isinstance(stmt, pycparser.c_ast.Decl):
            if isinstance(stmt.type, pycparser.c_ast.Struct):
                parse_struct_or_union(c_types, py_types, stmt.type, stmt.type.name)
            elif isinstance(stmt.type, pycparser.c_ast.Union):
                parse_struct_or_union(c_types, py_types, stmt.type, stmt.type.name)
            elif isinstance(stmt.type, pycparser.c_ast.Enum):
                parse_enum(c_types, py_types, stmt.type, stmt.type.name)
            else:
                pass
        elif isinstance(stmt, pycparser.c_ast.Typedef):
            parse_typedef(c_types, py_types, stmt)
        else:
            pass


filename = pathlib.Path("prov_ops.h")
ast = pycparser.parse_file(filename, use_cpp=True, cpp_args="-DPYCPARSER")
c_types = dict(default_c_types)
py_types = dict(default_py_types)
parse_all_types(c_types, py_types, ast.ext)


for key in c_types.keys() - default_c_types.keys():
    if key[0] in {"struct", "union", "enum"}:
        print(key, repr(c_types[key]))
