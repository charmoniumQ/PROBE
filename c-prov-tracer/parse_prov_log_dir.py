import os
import enum
import typing
import ctypes
import pathlib
import struct_parser
import pycparser # type: ignore
import arena.parse_arena


c_types = dict(struct_parser.default_c_types)
py_types = dict(struct_parser.default_py_types)


filename = pathlib.Path("prov_ops.h")
ast = pycparser.parse_file(filename, use_cpp=True, cpp_args="-DPYCPARSER")
struct_parser.parse_all_types(ast.ext, c_types, py_types)


# for key in c_types.keys() - struct_parser.default_c_types.keys():
#     if key[0] in {"struct", "union", "enum"}:
#         print(struct_parser.c_type_to_c_source(c_types[key]))


COp = c_types[("struct", "Op")]
Op = py_types[("struct", "Op")]
OpCode: enum.EnumType = py_types[("enum", "OpCode")]  # type: ignore


def align(ptr: int, alignment: int) -> int:
    assert alignment != 0 and (alignment & (alignment - 1)) == 0
    return (ptr + alignment - 1) & (~(alignment - 1))


def parse_thread_dir(ops_dir: pathlib.Path, data_dir: pathlib.Path) -> typing.Sequence[Op]:
    op_memory_segments = arena.parse_arena.parse_arena_dir(ops_dir)
    data_memory_segments = arena.parse_arena.parse_arena_dir(data_dir)
    memory_segments = sorted([*op_memory_segments, *data_memory_segments], key=lambda mem_seg: mem_seg.start)
    memory = arena.parse_arena.MemorySegments(memory_segments)
    def info(fields: typing.Mapping[str, typing.Any], field_name: str) -> typing.Any:
        if field_name == "data":
            op_code_to_union_variant = {
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
            }
            return op_code_to_union_variant[fields["op_code"]]
        else:
            return None
    ops: list[Op] = []
    for memory_segment in op_memory_segments:
        assert (memory_segment.stop - memory_segment.start) % ctypes.sizeof(COp) == 0
        for op_start in range(memory_segment.start, memory_segment.stop, ctypes.sizeof(COp)):
            elem_buffr = memory_segment[op_start : op_start + ctypes.sizeof(COp)]
            assert len(elem_buffr) == ctypes.sizeof(COp)
            c_op = COp.from_buffer_copy(elem_buffr)
            py_op = struct_parser.convert_c_obj_to_py_obj(c_op, Op, info, memory)
            assert isinstance(py_op, Op)
            ops.append(py_op)
    return ops


def parse_prov_log_dir(prov_log_dir: pathlib.Path) -> typing.Sequence[typing.Sequence[Op]]:
    all_ops = list[list[Op]]()
    for f0 in prov_log_dir.iterdir():
        for f1 in f0.iterdir():
            for f2 in f1.iterdir():
                for f3 in f2.iterdir():
                    for f4 in f3.iterdir():
                        assert (f4 / "data").exists()
                        assert (f4 / "ops").exists()
                        all_ops.append(parse_thread_dir(f4 / "ops", f4 / "data"))
    return all_ops

if __name__ == "__main__":
    prov_log_dir = pathlib.Path(os.environ.get("PROV_LOG_DIR", ".prov"))
    all_ops = parse_prov_log_dir(prov_log_dir)
    for thread_ops in all_ops:
        for op in thread_ops:
            print(op.data)
        print()
