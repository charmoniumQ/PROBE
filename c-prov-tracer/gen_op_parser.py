import enum
import typing
import ctypes
import pathlib
import struct_parser
import pycparser # type: ignore


filename = pathlib.Path("prov_ops.h")
ast = pycparser.parse_file(filename, use_cpp=True, cpp_args="-DPYCPARSER")
c_types, py_types = struct_parser.parse_all_types(ast.ext)
# for key in c_types.keys() - struct_parser.default_c_types.keys():
#     if key[0] in {"struct", "union", "enum"}:
#         print(struct_parser.c_type_to_c_source(c_types[key]))


COp = c_types[("struct", "Op")]
Op = py_types[("struct", "Op")]
OpCode: enum.EnumType = py_types[("enum", "OpCode")]


def parse_prov_log(prov_log_file: pathlib.Path) -> list[Op]:
    buffr = prov_log_file.read_bytes()
    mem_segs = struct_parser.MemorySegments(
        [struct_parser.MemorySegment(buffr, 0, len(buffr))],
    )
    assert len(buffr) % ctypes.sizeof(COp) == 0
    size = ctypes.sizeof(COp)
    def info(fields: typing.Mapping[str, typing.Any], field_name: str) -> typing.Any:
        return {
            OpCode.init_process_op_code: ("init_process", None),
            OpCode.init_thread_op_code: ("init_thread", None),
            OpCode.open_op_code: ("open", None),
            OpCode.close_op_code: ("close", None),
            OpCode.chdir_op_code: ("chdir", None),
            OpCode.exec_op_code: ("exec", None),
            OpCode.clone_op_code: ("clone", None),
            OpCode.exit_op_code: ("exit", None),
            OpCode.access_op_code: ("access", None),
            OpCode.stat_op_code: ("stat", None),
            OpCode.chown_op_code: ("chown", None),
            OpCode.chmod_op_code: ("chmod", None),
            OpCode.read_link_op_code: ("read_link", None),
        }.get(fields.get("op_code"))
    for idx in range(0, len(buffr) // ctypes.sizeof(COp)):
        c_obj = COp.from_buffer_copy(buffr[idx * size : (idx + 1) * size])
        print(struct_parser.convert_c_obj_to_py_obj(
            c_obj,
            Op,
            info,
            buffr,
        ))


if __name__ == "__main__":
    for prov_log_file in pathlib.Path(".prov").iterdir():
        parse_prov_log(prov_log_file)
        print()
