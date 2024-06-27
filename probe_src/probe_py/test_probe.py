from typer.testing import CliRunner
import tarfile
from .cli import app
from . import parse_probe_log
import pathlib
import typing

runner = CliRunner()

def test_diff_cmd():
    result = runner.invoke(app,["record","--make","diff","../flake.nix","../flake.lock"])
    input: pathlib.Path = pathlib.Path("probe_log")
    assert input.exists()
    probe_log_tar_obj = tarfile.open(input, "r")
    process_tree_prov_log = parse_probe_log.parse_probe_log_tar(probe_log_tar_obj)
    probe_log_tar_obj.close()
    paths = ['../flake.nix','../flake.lock']
    fileDescriptors = []
    reservedFileDescriptors = [0, 1, 2]
    
    for pid,process in process_tree_prov_log.processes.items():
        # before start of every process all files should be closed
        assert len(fileDescriptors) == 0
        fileDescriptors = []
        count = 0
        firstThread = True
        for epochid,exec_epoch in process.exec_epochs.items():
            # check the order of exec_epoch
            assert epochid == count
            count=count+1
            for tid,thread in exec_epoch.threads.items():
                if firstThread:
                    # the main thread id should be equal to first thread id
                    assert tid==pid
                    firstThread = False
                check_open_close(thread.ops,paths)
                # for op in thread.ops:
                #     if isinstance(op.data,parse_probe_log.InitExecEpochOp):
                #         assert op.data.program_name == "diff"
                #     elif isinstance(op.data,parse_probe_log.OpenOp):
                #         path = op.data.path.path
                #         if path != '/proc/self/maps':
                #             assert paths[0] == path
                #             paths.pop(0)
                #         fileDescriptor = op.data.fd
                #         fileDescriptors.append(fileDescriptor)
                #     elif isinstance(op.data,parse_probe_log.CloseOp):
                #         fileDescriptor = op.data.low_fd
                #         if fileDescriptor in reservedFileDescriptors:
                #             continue
                #         assert fileDescriptor in fileDescriptors
                #         fileDescriptors.remove(fileDescriptor)

def test_bash_in_bash():
    result = runner.invoke(app,["record", "bash", "-c", "head ../flake.nix ; head ../flake.lock ; head ../flake.nix"])
    assert result.exit_code == 0
    input: pathlib.Path = pathlib.Path("probe_log")
    assert input.exists()
    probe_log_tar_obj = tarfile.open(input, "r")
    process_tree_prov_log = parse_probe_log.parse_probe_log_tar(probe_log_tar_obj)
    probe_log_tar_obj.close()
    paths = ['../flake.nix','../flake.lock','../flake.nix']
    global current_child_process
    current_child_process = 0
    parentProcess = list(process_tree_prov_log.processes.values())[0]
   
    first_epoch_ops = []
    for epochid, exec_epoch in parentProcess.exec_epochs.items():
        for tid,threads in exec_epoch.threads.items():
            if epochid != 0:
                assert check_open_close(threads.ops, [])
            else:
                first_epoch_ops = threads.ops

    op_idx = 0
    while op_idx < len(first_epoch_ops):
        op = first_epoch_ops[op_idx]
        
        if isinstance(op.data,parse_probe_log.CloneOp):
            current_child_process=current_child_process + 1
            child_process_id = op.data.child_process_id
            op = first_epoch_ops[op_idx+1]
            assert (isinstance(op.data,parse_probe_log.WaitOp) and op.data.options == 0 and op.data.ret == child_process_id)
            op = first_epoch_ops[op_idx+2]
            assert (isinstance(op.data,parse_probe_log.WaitOp) and op.data.options == 1 and op.data.ret == 0)
            child_process_ops = process_tree_prov_log.processes[child_process_id].exec_epochs[1].threads[child_process_id].ops
            assert check_open_close(child_process_ops, [paths[current_child_process-1]])
            op_idx+=3
        else:
            op_idx+=1
    
    # number of clone operations is number of commands-1
    assert current_child_process == len(paths)-1


def check_open_close(ops:typing.Sequence[parse_probe_log.Op], paths):
    reservedFileDescriptors = [0, 1, 2]
    fileDescriptors = []
    for op in ops:
        if isinstance(op.data,parse_probe_log.OpenOp):
            path = op.data.path.path
            if path in paths:
                if paths[0] != path:
                    return False
                paths.pop(0)
                fileDescriptor = op.data.fd
                fileDescriptors.append(fileDescriptor)
        elif isinstance(op.data,parse_probe_log.CloseOp):
                fileDescriptor = op.data.low_fd
                if fileDescriptor in reservedFileDescriptors:
                    continue
                if fileDescriptor not in fileDescriptors:
                    return False
                fileDescriptors.remove(fileDescriptor)
        return True
        
    