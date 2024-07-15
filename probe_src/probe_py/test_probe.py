import tarfile
from .cli import record
from . import parse_probe_log
from . import analysis
import pathlib
import networkx as nx
import subprocess
import typer
import pytest


def test_diff_cmd():
    command = [
     'diff', '../flake.nix', '../flake.lock'
    ]
    process_tree_prov_log = execute_command(command, 1)
    process_graph = analysis.provlog_to_digraph(process_tree_prov_log)
    paths = ['../flake.nix','../flake.lock']
    dfs_edges = list(nx.dfs_edges(process_graph))
    match_open_and_close_fd(dfs_edges, process_tree_prov_log, paths)
    

def test_bash_in_bash():
    command = ["bash", "-c", "head ../flake.nix ; head ../flake.lock"]
    process_tree_prov_log = execute_command(command)
    process_graph = analysis.provlog_to_digraph(process_tree_prov_log)
    paths = ['../flake.nix', '../flake.lock']
    process_file_map = {}
    dfs_edges = list(nx.dfs_edges(process_graph))
    parent_process_id = dfs_edges[0][0][0]
    process_file_map[paths[len(paths)-1]] = parent_process_id
    check_for_clone_and_open(dfs_edges, process_tree_prov_log, len(paths)-1, process_file_map, paths)

def test_bash_in_bash_pipe():
    command = ["bash", "-c", "head ../flake.nix | tail"]
    process_tree_prov_log = execute_command(command)
    process_graph = analysis.provlog_to_digraph(process_tree_prov_log)
    paths = ['../flake.nix','stdout']
    dfs_edges = list(nx.dfs_edges(process_graph))
    check_for_clone_and_open(dfs_edges, process_tree_prov_log, len(paths), {}, paths)
    
        
def test_pthreads():
    process = subprocess.Popen(["gcc", "tests/c/createFile.c", "-o", "test"])
    process.communicate()
    process_tree_prov_log = execute_command(["./test"])
    process_graph = analysis.provlog_to_digraph(process_tree_prov_log)
    dfs_edges = list(nx.dfs_edges(process_graph))
    total_pthreads = 3
    paths = ['/tmp/0.txt', '/tmp/1.txt', '/tmp/2.txt']
    check_pthread_graph(dfs_edges, process_tree_prov_log, total_pthreads, paths)
    
def execute_command(command, return_code=0):
    input = pathlib.Path("probe_log")
    with pytest.raises(typer.Exit) as excinfo:
        record(command, False, False, False,input)
    assert excinfo.value.exit_code == return_code
    # result = subprocess.run(['./PROBE', 'record'] + command, capture_output=True, text=True, check=True)
    assert input.exists()
    probe_log_tar_obj = tarfile.open(input, "r")
    process_tree_prov_log = parse_probe_log.parse_probe_log_tar(probe_log_tar_obj)
    probe_log_tar_obj.close()
    return process_tree_prov_log


def check_for_clone_and_open(dfs_edges, process_tree_prov_log, number_of_child_process, process_file_map, paths):
    # to ensure files which are opened are closed
    file_descriptors = []
    # to ensure WaitOp ret is same as the child process pid
    check_wait = []
    # to ensure the child process has ExecOp, OpenOp and CloseOp
    check_child_processes = []
    # to ensure child process touch the right file

    parent_process_id = dfs_edges[0][0][0]
    reserved_file_descriptors = [0, 1, 2]
    current_child_process = 0

    for edge in dfs_edges:
        curr_pid, curr_epoch_idx, curr_tid, curr_op_idx = edge[0]
        
        curr_node_op = get_op_from_provlog(process_tree_prov_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if curr_node_op!=None:
            curr_node_op = curr_node_op.data
        if(isinstance(curr_node_op,parse_probe_log.CloneOp)):
            next_op = get_op_from_provlog(process_tree_prov_log, edge[1][0], edge[1][1], edge[1][2], edge[1][3])
            if next_op!=None:
                next_op = next_op.data
            if isinstance(next_op,parse_probe_log.ExecOp):
                assert edge[1][0] == curr_node_op.task_id
                check_child_processes.append(curr_node_op.task_id)
                continue
            if isinstance(next_op,parse_probe_log.CloseOp) and edge[0][0]!=edge[1][0]:
                assert edge[1][0] == curr_node_op.task_id
                check_child_processes.append(curr_node_op.task_id)
                continue
            if edge[1][3] == -1:
                continue
            current_child_process+=1
            check_wait.append(curr_node_op.task_id)
            if len(paths)!=0:
                process_file_map[paths[current_child_process-1]] = curr_node_op.task_id
        elif(isinstance(curr_node_op,parse_probe_log.WaitOp)):
            ret_pid = curr_node_op.task_id
            wait_option = curr_node_op.options
            if wait_option == 0:
                assert ret_pid in check_wait
                check_wait.remove(ret_pid)
        if(isinstance(curr_node_op,parse_probe_log.OpenOp)):
            file_descriptors.append(curr_node_op.fd)
            path = curr_node_op.path.path
            if path in paths:
                if len(process_file_map.keys())!=0:
                    # ensure the right cloned process has OpenOp for the path
                    assert curr_pid == process_file_map[path]
                    if curr_pid!=parent_process_id:
                        assert curr_pid in check_child_processes
                        check_child_processes.remove(curr_pid)
        elif(isinstance(curr_node_op,parse_probe_log.CloseOp)):
            fd = curr_node_op.low_fd
            if fd in reserved_file_descriptors:
                continue
            if curr_node_op.ferrno != 0:
                continue
            if fd in file_descriptors:
                file_descriptors.remove(fd)
        elif(isinstance(curr_node_op,parse_probe_log.ExecOp)):
            # check if stdout is read in right child process
            if(edge[1][3]==-1):
                continue
            next_init_op = get_op_from_provlog(process_tree_prov_log,curr_pid,1,curr_pid,0)
            if next_init_op!=None:
                next_init_op = next_init_op.data
            if next_init_op.program_name == 'tail':
                assert process_file_map['stdout'] == curr_pid
                check_child_processes.remove(curr_pid)

    # check number of cloneOps
    assert current_child_process == number_of_child_process
    # check if every cloneOp has a WaitOp
    assert len(check_wait) == 0
    assert len(process_file_map.items()) == len(paths)
    assert len(check_child_processes) == 0
    assert len(file_descriptors) == 0


def match_open_and_close_fd(dfs_edges, process_tree_prov_log, paths):
    reserved_file_descriptors = [0, 1, 2]
    file_descriptors = []
    for edge in dfs_edges:
        curr_pid, curr_epoch_idx, curr_tid, curr_op_idx = edge[0]
        curr_node_op = get_op_from_provlog(process_tree_prov_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if curr_node_op!=None:
            curr_node_op = curr_node_op.data
        if(isinstance(curr_node_op,parse_probe_log.OpenOp)):
            file_descriptors.append(curr_node_op.fd)
            path = curr_node_op.path.path
            if path in paths:
                paths.remove(path)
        elif(isinstance(curr_node_op,parse_probe_log.CloseOp)):
            fd = curr_node_op.low_fd
            if fd in reserved_file_descriptors:
                continue
            if curr_node_op.ferrno != 0:
                continue
            if fd in file_descriptors:
                file_descriptors.remove(fd)
                
    assert len(file_descriptors) == 0
    assert len(paths) == 0

def check_pthread_graph(dfs_edges, process_tree_prov_log, total_pthreads, paths):
    check_wait = []
    process_file_map = {}
    current_child_process = 0
    file_descriptors = []
    reserved_file_descriptors = [1, 2, 3]
    edge = dfs_edges[0]
    parent_pthread_id = get_op_from_provlog(process_tree_prov_log, edge[0][0], edge[0][1], edge[0][2], edge[0][3]).pthread_id

    for edge in dfs_edges:
        curr_pid, curr_epoch_idx, curr_tid, curr_op_idx = edge[0]
        curr_node_op = get_op_from_provlog(process_tree_prov_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        print(curr_node_op.data)
        if(isinstance(curr_node_op.data,parse_probe_log.CloneOp)):
            next_op = get_op_from_provlog(process_tree_prov_log, edge[1][0], edge[1][1], edge[1][2], edge[1][3])
            if edge[1][2] != curr_tid:
               assert curr_node_op.data.task_id == next_op.pthread_id
               continue
            check_wait.append(curr_node_op.data.task_id)
            if len(paths)!=0:
                process_file_map[paths[current_child_process]] = curr_node_op.data.task_id
            current_child_process+=1
        elif(isinstance(curr_node_op.data,parse_probe_log.WaitOp)):
            ret_pid = curr_node_op.data.task_id
            wait_option = curr_node_op.data.options
            if wait_option == 0:
                assert ret_pid in check_wait
                check_wait.remove(ret_pid)
        elif(isinstance(curr_node_op.data,parse_probe_log.OpenOp)):
            file_descriptors.append(curr_node_op.data.fd)
            path = curr_node_op.data.path.path
            # print(curr_node_op.data)
            # print(edge)
            # next_op = get_op_from_provlog(process_tree_prov_log, edge[1][0], edge[1][1], edge[1][2], edge[1][3])
            # print(next_op.data)
            # print(file_descriptors)
            # print(">>>>>>>>>>>>>>>>>>>>>")
            if path in paths:
                if len(process_file_map.keys())!=0 and parent_pthread_id!=curr_node_op.pthread_id:
                    # ensure the right cloned process has OpenOp for the path
                    assert process_file_map[path] == curr_node_op.pthread_id
        elif(isinstance(curr_node_op.data, parse_probe_log.CloseOp)):
            fd = curr_node_op.data.low_fd
            print(curr_node_op.data)
            if fd in reserved_file_descriptors:
                continue
            if curr_node_op.data.ferrno != 0:
                continue
            assert fd in file_descriptors
            if fd in file_descriptors:
                file_descriptors.remove(fd)
            
            print(file_descriptors)
            print("after close")
        
    # check number of cloneOps
    assert current_child_process == total_pthreads
    # check if every cloneOp has a WaitOp
    assert len(check_wait) == 0
    # for every file there is a pthread
    assert len(process_file_map.items()) == len(paths)
    assert len(file_descriptors) == 0

def get_op_from_provlog(process_tree_prov_log, pid, exec_epoch_id, tid,op_idx):
    if op_idx == -1 or exec_epoch_id == -1:
        return None
    return process_tree_prov_log.processes[pid].exec_epochs[exec_epoch_id].threads[tid].ops[op_idx]