import os
import tarfile
import enum
import typing
import ctypes
import pathlib
import pycparser # type: ignore
import arena.parse_arena as arena
from . import struct_parser


c_types = dict(struct_parser.default_c_types)
py_types = dict(struct_parser.default_py_types)


filename = pathlib.Path(__file__).parent.parent / "libprobe/include/prov_ops.h"
assert filename.exists()
ast = pycparser.parse_file(filename, use_cpp=True, cpp_args="-DPYCPARSER")
struct_parser.parse_all_types(ast.ext, c_types, py_types)


# for key in c_types.keys() - struct_parser.default_c_types.keys():
#     if key[0] in {"struct", "union", "enum"}:
#         print(struct_parser.c_type_to_c_source(c_types[key]))


COp = c_types[("struct", "Op")]
Op: typing.TypeAlias = py_types[("struct", "Op")]
OpCode: enum.EnumType = py_types[("enum", "OpCode")]  # type: ignore


def align(ptr: int, alignment: int) -> int:
    assert alignment != 0 and (alignment & (alignment - 1)) == 0
    return (ptr + alignment - 1) & (~(alignment - 1))


def parse_segments(op_segments: arena.MemorySegments, data_segments: arena.MemorySegments) -> typing.Sequence[Op]:
    memory_segments = sorted([*op_segments, *data_segments], key=lambda mem_seg: mem_seg.start)
    memory = arena.MemorySegments(memory_segments)
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
    for memory_segment in op_segments:
        assert (memory_segment.stop - memory_segment.start) % ctypes.sizeof(COp) == 0
        for op_start in range(memory_segment.start, memory_segment.stop, ctypes.sizeof(COp)):
            elem_buffr = memory_segment[op_start : op_start + ctypes.sizeof(COp)]
            assert len(elem_buffr) == ctypes.sizeof(COp)
            c_op = COp.from_buffer_copy(elem_buffr)
            py_op = struct_parser.convert_c_obj_to_py_obj(c_op, Op, info, memory)
            assert isinstance(py_op, Op)
            ops.append(py_op)
    return ops


def parse_thread_dir(ops_dir: pathlib.Path, data_dir: pathlib.Path) -> tuple[arena.MemorySegment, arena.MemorySegment]:
    return (
        arena.parse_arena_dir(ops_dir),
        arena.parse_arena_dir(data_dir),
    )


def parse_thread_dir_tar(
        tar: tarfile.TarFile,
        ops_dir_prefix: pathlib.Path,
        data_dir_prefix: pathlib.Path,
) -> tuple[arena.MemorySegment, arena.MemorySegment]:
    return (
        arena.parse_arena_dir_tar(tar, ops_dir_prefix),
        arena.parse_arena_dir_tar(tar, data_dir_prefix),
    )


def parse_probe_log_dir(probe_log_dir: pathlib.Path) -> typing.Sequence[typing.Sequence[Op]]:
    all_ops = list[list[Op]]()
    for f0 in probe_log_dir.iterdir():
        for f1 in f0.iterdir():
            for f2 in f1.iterdir():
                for f3 in f2.iterdir():
                    for f4 in f3.iterdir():
                        assert (f4 / "data").exists()
                        assert (f4 / "ops").exists()
                        all_ops.append(parse_segments(*parse_thread_dir(f4 / "ops", f4 / "data")))
    return all_ops


def parse_probe_log_tar(probe_log_tar: tarfile.TarFile) -> typing.Sequence[typing.Sequence[Op]]:
    member_paths = sorted([
        pathlib.Path(name)
        for name in probe_log_tar.getnames()
    ])
    all_ops = list[list[Op]]()
    for member in member_paths:
        if len(member.parts) == 5:
            assert member / "ops" in member_paths
            assert member / "data" in member_paths
            all_ops.append(parse_segments(*parse_thread_dir_tar(probe_log_tar, member / "ops", member / "data")))
    return all_ops
