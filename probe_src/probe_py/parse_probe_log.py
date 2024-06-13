import collections
import dataclasses
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

# echo '#define _GNU_SOURCE\n#include <sched.h>\nCLONE_THREAD' | cpp | tail --lines=1
CLONE_THREAD = 0x00010000


COp = c_types[("struct", "Op")]
Op: typing.TypeAlias = py_types[("struct", "Op")]
InitExecEpochOp: typing.TypeAlias = py_types[("struct", "InitExecEpochOp")]
InitThreadOp: typing.TypeAlias = py_types[("struct", "InitThreadOp")]
CloneOp: typing.TypeAlias = py_types[("struct", "CloneOp")]
ExecOp: typing.TypeAlias = py_types[("struct", "ExecOp")]
WaitOp: typing.TypeAlias = py_types[("struct", "WaitOp")]
OpCode: enum.EnumType = py_types[("enum", "OpCode")]


@dataclasses.dataclass
class ThreadProvLog:
    sams_thread_id: int
    ops: typing.Sequence[Op]  # type: ignore

    @property
    def init_op(self) -> InitThreadOp:
        init_op = self.ops[1 if isinstance(self.ops[0].data, InitExecEpochOp) else 0].data
        assert isinstance(init_op, InitThreadOp)
        return init_op


@dataclasses.dataclass
class ExecEpochProvLog:
    exec_epoch: int
    threads: typing.Mapping[int, ThreadProvLog]

    @property
    def init_op(self) -> InitThreadOp:
        init_op = self.threads[0][0]
        assert isinstance(init_op, InitExecEpochOp)
        return init_op


@dataclasses.dataclass
class ProcessProvLog:
    pid: int
    birth_time: int
    exec_epochs: typing.Mapping[int, ExecEpochProvLog]


@dataclasses.dataclass
class ProcessTreeProvLog:
    processes: typing.Mapping[int, ProcessProvLog]


def parse_segments(op_segments: arena.MemorySegments, data_segments: arena.MemorySegments) -> ThreadProvLog:
    memory_segments = sorted([*op_segments, *data_segments], key=lambda mem_seg: mem_seg.start)
    memory = arena.MemorySegments(memory_segments)
    def info(fields: typing.Mapping[str, typing.Any], field_name: str) -> typing.Any:
        if field_name == "data":
            op_code_to_union_variant = {
                OpCode.init_exec_epoch_op_code: ("init_exec_epoch", None),
                OpCode.init_thread_op_code: ("init_thread", None),
                OpCode.open_op_code: ("open", None),
                OpCode.close_op_code: ("close", None),
                OpCode.chdir_op_code: ("chdir", None),
                OpCode.exec_op_code: ("exec", None),
                OpCode.clone_op_code: ("clone", None),
                OpCode.exit_op_code: ("exit", None),
                OpCode.access_op_code: ("access", None),
                OpCode.stat_op_code: ("stat", None),
                OpCode.readdir_op_code: ("readdir", None),
                OpCode.wait_op_code: ("wait", None),
                OpCode.getrusage_op_code: ("getrusage", None),
                OpCode.update_metadata_op_code: ("update_metadata", None),
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
    thread_op_idx = 1 if isinstance(ops[0].data, InitExecEpochOp) else 0
    assert isinstance(ops[thread_op_idx].data, InitThreadOp)
    return ThreadProvLog(ops[thread_op_idx].data.sams_thread_id, ops)


def parse_probe_log_dir(probe_log_dir: pathlib.Path) -> ProcessTreeProvLog:
    processes = dict[int, ProcessProvLog]()
    for f0 in probe_log_dir.iterdir():
        for f1 in f0.iterdir():
            for f2 in f1.iterdir():
                exec_epochs = dict[int, ExecEpochProvLog]()
                for f3 in f2.iterdir():
                    threads = dict[int, ThreadProvLog]()
                    for f4 in f3.iterdir():
                        assert (f4 / "data").exists()
                        assert (f4 / "ops").exists()
                        data_segments = arena.parse_arena_dir(f4 / "data")
                        op_segments = arena.parse_arena_dir(f4 / "ops")
                        thread_prov = parse_segments(op_segments, data_segments)
                        threads[thread_prov.init_op.sams_thread_id] = thread_prov
                    if threads:
                        epoch = threads.values()[0].init_op.exec_epoch
                        exec_epochs[epoch] = ExecEpochProvLog(epoch, threads)
                if exec_epochs:
                    processes[exec_epoch.init_op.pid] = ProcessProvLog(
                        exec_epoch.init_op.pid,
                        exec_epoch.init_op.pid.birth_time.tv_sec * 10**9 + exec_epoch.init_op.pid.birth_time.tv_nsec,
                        exec_epochs,
                    )
    return ProcessTreeProvLog(processes)


def parse_probe_log_tar(probe_log_tar: tarfile.TarFile) -> ProcessTreeProvLog:
    member_paths = sorted([
        pathlib.Path(name)
        for name in probe_log_tar.getnames()
    ])
    threads = collections.defaultdict[(int, float), dict[int, dict[int, ThreadProvLog]]](
        lambda: collections.defaultdict[int, dict[int, ThreadProvLog]](
            collections.defaultdict[dict[int, ThreadProvLog]]
        )
    )
    for member in member_paths:
        if len(member.parts) == 5:
            assert member / "ops" in member_paths
            assert member / "data" in member_paths
            op_segments = arena.parse_arena_dir_tar(probe_log_tar, member / "ops")
            data_segments = arena.parse_arena_dir_tar(probe_log_tar, member / "data")
            thread = parse_segments(op_segments, data_segments)
            op = thread.init_op
            process_id = (op.process_id, op.process_birth_time.tv_sec * 10**9 + op.process_birth_time.tv_nsec)
            threads[process_id][op.exec_epoch][op.sams_thread_id] = thread
    return ProcessTreeProvLog({
        process_id: ProcessProvLog(
            process_id[0],
            process_id[1],
            {
                exec_epoch_id: ExecEpochProvLog(exec_epoch_id, threads)
                for exec_epoch_id, threads in exec_epochs.items()
            },
        )
        for process_id, exec_epochs in threads.items()
    })
