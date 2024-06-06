import ctypes
import pathlib
import struct_parser
import pycparser # type: ignore


filename = pathlib.Path("prov_ops.h")
ast = pycparser.parse_file(filename, use_cpp=True, cpp_args="-DPYCPARSER")
c_types, py_types = struct_parser.parse_all_types(ast.ext)
for key in c_types.keys() - struct_parser.default_c_types.keys():
    if key[0] in {"struct", "union", "enum"}:
        print(struct_parser.c_type_to_c_source(c_types[key]))


COp = c_types[("struct", "Op")]
Op = py_types[("struct", "Op")]


def parse_prov_log(prov_log_file: pathlib.Path) -> list[Op]:
    buff = prov_log_file.read_bytes()
    assert len(buff) % ctypes.sizeof(COp) == 0
    for offset in range(0, len(buff) // ctypes.sizeof(COp)):
        print(struct_parser.convert_c_bytes_to_py_obj(
            c_types,
            py_types,
            ("struct", "Op"),
            buff[offset * ctypes.sizeof(COp) : (offset + 1) * ctypes.sizeof(COp)],
        ))


if __name__ == "__main__":
    for prov_log_file in pathlib.Path(".prov").iterdir():
        parse_prov_log(prov_log_file)
        print()
