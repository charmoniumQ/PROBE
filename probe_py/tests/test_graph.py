import pytest
import typing
from probe_py.parser import parse_probe_log
from probe_py.ptypes import ProbeLog, Pid, ExecNo, Tid
from probe_py.ops import OpenOp, CloneOp, ExecOp, InitExecEpochOp, CloseOp, WaitOp, Op
from probe_py.analysis import probe_log_to_hb_graph, validate_hb_graph
import pathlib
import networkx as nx
import subprocess

Node: typing.TypeAlias = tuple[Pid, ExecNo, Tid, int]
DEBUG_LIBPROBE = False
REMAKE_LIBPROBE = False


project_root = pathlib.Path(__file__).resolve().parent.parent.parent


def test_diff_cmd() -> None:
    assert False
    paths = [str(project_root / "flake.nix"), str(project_root / "flake.lock")]
    command = ['diff', *paths]
    probe_log = execute_command(command, 1)
    hb_graph = probe_log_to_hb_graph(probe_log)
    assert not validate_hb_graph(probe_log, hb_graph)
    path_bytes = [path.encode() for path in paths]
    dfs_edges = list(nx.dfs_edges(hb_graph))
    match_open_and_close_fd(dfs_edges, probe_log, path_bytes)


def test_bash_in_bash() -> None:
    command = ["bash", "-c", f"head {project_root}/flake.nix ; head {project_root}/flake.lock"]
    probe_log = execute_command(command)
    hb_graph = probe_log_to_hb_graph(probe_log)
    assert not validate_hb_graph(probe_log, hb_graph)
    paths = [f'{project_root}/flake.nix'.encode(), f'{project_root}/flake.lock'.encode()]
    process_file_map = {}
    start_node = [
        node
        for node in hb_graph.nodes()
        if hb_graph.in_degree(node) == 0
    ][0]
    dfs_edges = list(nx.dfs_edges(hb_graph,source=start_node))
    parent_process_id = dfs_edges[0][0][0]
    process_file_map[f"{project_root}/flake.lock".encode()] = parent_process_id
    process_file_map[f"{project_root}/flake.nix".encode()] = parent_process_id
    check_for_clone_and_open(dfs_edges, probe_log, 1, process_file_map, paths)

def test_bash_in_bash_pipe() -> None:
    command = ["bash", "-c", f"head {project_root}/flake.nix | tail"]
    probe_log = execute_command(command)
    hb_graph = probe_log_to_hb_graph(probe_log)
    assert not validate_hb_graph(probe_log, hb_graph)
    paths = [f'{project_root}/flake.nix'.encode(), b'stdout']
    start_node = [
        node
        for node in hb_graph.nodes()
        if hb_graph.in_degree(node) == 0
    ][0]
    dfs_edges = list(nx.dfs_edges(hb_graph,source=start_node))
    check_for_clone_and_open(dfs_edges, probe_log, len(paths), {}, paths)


@pytest.mark.xfail
def test_pthreads() -> None:
    probe_log = execute_command([f"{project_root}/tests/examples/createFile.exe"])
    hb_graph = probe_log_to_hb_graph(probe_log)
    assert not validate_hb_graph(probe_log, hb_graph)
    root_node = [n for n in hb_graph.nodes() if hb_graph.out_degree(n) > 0 and hb_graph.in_degree(n) == 0][0]
    bfs_nodes = [node for layer in nx.bfs_layers(hb_graph, root_node) for node in layer]
    root_node = [n for n in hb_graph.nodes() if hb_graph.out_degree(n) > 0 and hb_graph.in_degree(n) == 0][0]
    dfs_edges = list(nx.dfs_edges(hb_graph,source=root_node))
    total_pthreads = 3
    paths = [b'/tmp/0.txt', b'/tmp/1.txt', b'/tmp/2.txt']
    check_pthread_graph(bfs_nodes, dfs_edges, probe_log, total_pthreads, paths)
    
def execute_command(command: list[str], return_code: int = 0) -> ProbeLog:
    input = pathlib.Path("probe_log")
    if input.exists():
        input.unlink()
    result = subprocess.run(
        ['probe', 'record'] + (["--debug"] if DEBUG_LIBPROBE else []) + (["--make"] if REMAKE_LIBPROBE else []) + command,
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout)
    print(result.stderr)
    # TODO: Discuss if PROBE should preserve the returncode.
    # The Rust CLI currently does not
    # assert result.returncode == return_code
    assert result.returncode == 0
    assert input.exists()
    probe_log = parse_probe_log(input)
    return probe_log


def check_for_clone_and_open(
        dfs_edges: typing.Sequence[tuple[Node, Node]],
        probe_log: ProbeLog,
        number_of_child_process: int,
        process_file_map: dict[bytes, Pid],
        paths: list[bytes],
) -> None:
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
        
        curr_node_op = get_op_from_probe_log(probe_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if curr_node_op is not None:
            curr_node_op_data = curr_node_op.data
        if(isinstance(curr_node_op_data,CloneOp)):
            next_op = get_op_from_probe_log(probe_log, edge[1][0], edge[1][1], edge[1][2], edge[1][3])
            if next_op is not None:
                next_op_data = next_op.data
            if isinstance(next_op_data,ExecOp):
                assert edge[1][0] == curr_node_op_data.task_id
                check_child_processes.append(curr_node_op_data.task_id)
                continue
            if isinstance(next_op_data, InitExecEpochOp):
                assert edge[1][0] == curr_node_op_data.task_id
                check_child_processes.append(curr_node_op_data.task_id)
                continue
            if isinstance(next_op_data,CloseOp) and edge[0][0]!=edge[1][0]:
                assert edge[1][0] == curr_node_op_data.task_id
                check_child_processes.append(curr_node_op_data.task_id)
                continue
            if edge[1][3] == -1:
                continue
            current_child_process+=1
            check_wait.append(curr_node_op_data.task_id)
            if len(paths)!=0:
                process_file_map[paths[current_child_process-1]] = Pid(curr_node_op_data.task_id)
        elif(isinstance(curr_node_op_data,WaitOp)):
            ret_pid = curr_node_op_data.task_id
            wait_option = curr_node_op_data.options
            if wait_option == 0:
                assert ret_pid in check_wait
                check_wait.remove(ret_pid)
        if(isinstance(curr_node_op_data,OpenOp)) and curr_node_op_data.ferrno == 0:
            file_descriptors.append(curr_node_op_data.fd)
            path = curr_node_op_data.path.path
            if path in paths:
                if len(process_file_map.keys())!=0:
                    # ensure the right cloned process has OpenOp for the path
                    assert curr_pid == process_file_map[path]
                    if curr_pid!=parent_process_id:
                        assert curr_pid in check_child_processes
                        check_child_processes.remove(curr_pid)
        elif(isinstance(curr_node_op_data,CloseOp)):
            fd = curr_node_op_data.fd
            if fd in reserved_file_descriptors:
                continue
            if curr_node_op_data.ferrno != 0:
                continue
            if fd in file_descriptors:
                file_descriptors.remove(fd)
        elif(isinstance(curr_node_op_data,ExecOp)):
            # check if stdout is read in right child process
            if(edge[1][3]==-1):
                continue
            next_init_op = get_op_from_probe_log(probe_log, curr_pid, ExecNo(1), curr_pid.main_thread(), 0)
            if next_init_op is not None:
                next_init_op_data = next_init_op.data
                assert isinstance(next_init_op_data, InitExecEpochOp)
            if next_init_op_data.exe.path.endswith(b'tail'):
                assert process_file_map[b'stdout'] == curr_pid
                check_child_processes.remove(curr_pid)

    # check number of cloneOps
    assert current_child_process == number_of_child_process
    # check if every cloneOp has a WaitOp
    assert len(check_wait) == 0
    assert len(process_file_map.items()) == len(paths)
    assert len(check_child_processes) == 0
    assert len(file_descriptors) == 0


def match_open_and_close_fd(
        dfs_edges: typing.Sequence[tuple[Node, Node]],
        probe_log: ProbeLog,
        paths: list[bytes],
) -> None:
    reserved_file_descriptors = [0, 1, 2]
    file_descriptors = set[int]()
    for edge in dfs_edges:
        curr_pid, curr_epoch_idx, curr_tid, curr_op_idx = edge[0]
        curr_node_op = get_op_from_probe_log(probe_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if curr_node_op is not None:
            curr_node_op_data = curr_node_op.data
        if(isinstance(curr_node_op_data,OpenOp)):
            file_descriptors.add(curr_node_op_data.fd)
            path = curr_node_op_data.path.path
            if path in paths:
                paths.remove(path)
        elif(isinstance(curr_node_op_data,CloseOp)):
            fd = curr_node_op_data.fd
            if fd in reserved_file_descriptors:
                continue
            if curr_node_op_data.ferrno != 0:
                continue
            assert fd in file_descriptors
            file_descriptors.remove(fd)

    assert len(file_descriptors) == 0
    assert len(paths) == 0

def check_pthread_graph(
        bfs_nodes: typing.Sequence[Node],
        dfs_edges: typing.Sequence[tuple[Node, Node]],
        probe_log: ProbeLog,
        total_pthreads: int,
        paths: list[bytes],
) -> None:
    check_wait = []
    process_file_map = {}
    current_child_process = 0
    file_descriptors = set[int]()
    reserved_file_descriptors = [1, 2, 3]
    edge = dfs_edges[0]
    parent_pthread_id = get_op_from_probe_log(probe_log, edge[0][0], edge[0][1], edge[0][2], edge[0][3]).pthread_id

    for edge in dfs_edges:
        curr_pid, curr_epoch_idx, curr_tid, curr_op_idx = edge[0]
        curr_node_op = get_op_from_probe_log(probe_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if(isinstance(curr_node_op.data,CloneOp)):
            if edge[1][2] != curr_tid:
               continue
            check_wait.append(curr_node_op.data.task_id)
            if len(paths)!=0:
                process_file_map[paths[current_child_process]] = curr_node_op.data.task_id
            current_child_process+=1
        if isinstance(curr_node_op.data,WaitOp):
            ret_pid = curr_node_op.data.task_id
            wait_option = curr_node_op.data.options
            if wait_option == 0:
                assert ret_pid in check_wait
                check_wait.remove(ret_pid)

    assert len(set(bfs_nodes)) == len(bfs_nodes)
    for node in bfs_nodes:
        curr_pid, curr_epoch_idx, curr_tid, curr_op_idx = node
        curr_node_op = get_op_from_probe_log(probe_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if curr_node_op is not None and (isinstance(curr_node_op.data,OpenOp)):
            file_descriptors.add(curr_node_op.data.fd)
            path = curr_node_op.data.path.path
            print("open", curr_tid, curr_node_op.pthread_id, curr_node_op.data.fd)
            if path in paths:
                if len(process_file_map.keys())!=0 and parent_pthread_id!=curr_node_op.pthread_id:
                    # ensure the right cloned process has OpenOp for the path
                    assert process_file_map[path] == curr_node_op.pthread_id
        elif curr_node_op is not None and (isinstance(curr_node_op.data, CloseOp)):
            fd = curr_node_op.data.fd
            print("close", curr_tid, curr_node_op.pthread_id, curr_node_op.data.fd)
            if fd in reserved_file_descriptors:
                continue
            if curr_node_op.data.ferrno != 0:
                continue
            assert fd in file_descriptors
            file_descriptors.remove(fd)

    # check number of cloneOps
    assert current_child_process == total_pthreads
    # check if every cloneOp has a WaitOp
    assert len(check_wait) == 0
    # for every file there is a pthread
    assert len(process_file_map.items()) == len(paths)
    assert len(file_descriptors) == 0

def get_op_from_probe_log(
        probe_log: ProbeLog,
        pid: Pid,
        exec_epoch_id: ExecNo,
        tid: Tid,
        op_idx: int,
) -> Op:
    if op_idx == -1 or exec_epoch_id == -1:
        raise ValueError()
    return probe_log.processes[pid].execs[exec_epoch_id].threads[tid].ops[op_idx]
