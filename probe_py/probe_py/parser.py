from __future__ import annotations
import tqdm
import dataclasses
import pathlib
import typing
import tarfile
import tempfile
import contextlib
import charmonium.time_block
import msgspec
from . import headers as ops
from .ptypes import ProbeLog, InodeVersion, Pid, ExecNo, Tid, Host, KernelThread, Process, Exec


@contextlib.contextmanager
def parse_probe_log_ctx(
        path_to_probe_log: pathlib.Path,
) -> typing.Iterator[ProbeLog]:
    """Parse probe log

    In this contextmanager, copied_files are extracted onto the disk.

    """
    with tempfile.TemporaryDirectory() as _tmpdir, charmonium.time_block.ctx("parse_probe_log_ctx", print_start=False):
        tmpdir = pathlib.Path(_tmpdir)
        with tarfile.open(path_to_probe_log, mode="r") as tar:
            tar.extractall(tmpdir, filter="data")
        host = Host.localhost()
        inodes = {
            InodeVersion.from_id_string(file.name): file
            for file in (tmpdir / "inodes").iterdir()
        }

        processes = dict[Pid, Process]()
        pid_entries = list((tmpdir / "pids").iterdir())
        for pid_dir in tqdm.tqdm(
                pid_entries,
                desc="parsing pid dirs",
        ):
            pid = Pid(pid_dir.name)
            execs = {}
            for epoch_dir in pid_dir.iterdir():
                exec_no = ExecNo(epoch_dir.name)
                threads = {}
                for tid_file in epoch_dir.iterdir():
                    tid = Tid(tid_file.name)
                    ops_list = msgspec.msgpack.decode(
                        tid_file.read_bytes(),
                        type=list[ops.Op],
                        strict=True,
                    )
                    assert ops_list
                    if not isinstance(ops_list[-1].data, (ops.ExitThread, ops.ExitProcess, ops.Exec)):
                        # Every thread should end in an ExitThread and possibly an ExitProcess
                        # Consider:
                        # void main() { pthread_create(thread2); }
                        # void thread2() { }
                        # The HB graph would be a tree, main[0] ---clone--> thread2[0].
                        # We can't put an HB edge from the last op of thread2 to the last op of main, and the HB graph 
                        ops_list.append(ops.Op(
                            data=ops.ExitThread(status=0),
                            pthread_id=ops_list[-1].pthread_id,
                            iso_c_thread_id=ops_list[-1].iso_c_thread_id,
                            ferrno=0,
                        ))
                    threads[tid] = KernelThread(tid, ops_list)
                execs[exec_no] = Exec(exec_no, threads)
            processes[pid] = Process(pid, execs)

        process_tree_context = msgspec.msgpack.decode(
            (tmpdir / "process_tree_context.msgpack").read_bytes(),
            type=ops.ProcessTreeContext,
            strict=True,
        )

        yield ProbeLog(
            processes,
            inodes,
            process_tree_context,
            host,
        )


def parse_probe_log(
        path_to_probe_log: pathlib.Path,
) -> ProbeLog:
    """Parse probe log.

    Unlike parse_probe_ctx, the copied_files will not be accessible.
    """
    with parse_probe_log_ctx(path_to_probe_log) as probe_log:
        return dataclasses.replace(
            probe_log,
            copied_files={},
            process_tree_context= msgspec.structs.replace(
                probe_log.process_tree_context,
                copy_files=ops.CopyFiles.NONE,
            ),
        )
