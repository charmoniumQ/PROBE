import typing
from probe_py.generated.parser import ProvLog, parse_probe_log
from probe_py.generated.ops import OpenOp, CloneOp, ExecOp, InitProcessOp, InitExecEpochOp, CloseOp, WaitOp, Op
from probe_py.manual.analysis import FileNode, ProcessNode
from probe_py.manual.workflows import NextflowGenerator
from . import analysis
import pathlib
import networkx as nx  # type: ignore
import subprocess
import re

Node: typing.TypeAlias = tuple[int, int, int, int]
DEBUG_LIBPROBE = False
REMAKE_LIBPROBE = False


project_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent


def test_diff_cmd() -> None:
    paths = [str(project_root / "flake.nix"), str(project_root / "flake.lock")]
    command = ['diff', *paths]
    process_tree_prov_log = execute_command(command, 1)
    process_graph = analysis.provlog_to_digraph(process_tree_prov_log)
    assert not analysis.validate_hb_graph(process_tree_prov_log, process_graph)
    path_bytes = [path.encode() for path in paths]
    dfs_edges = list(nx.dfs_edges(process_graph))
    match_open_and_close_fd(dfs_edges, process_tree_prov_log, path_bytes)


def test_bash_in_bash() -> None:
    command = ["bash", "-c", f"head {project_root}/flake.nix ; head {project_root}/flake.lock"]
    process_tree_prov_log = execute_command(command)
    process_graph = analysis.provlog_to_digraph(process_tree_prov_log)
    assert not analysis.validate_hb_graph(process_tree_prov_log, process_graph)
    paths = [f'{project_root}/flake.nix'.encode(), f'{project_root}/flake.lock'.encode()]
    process_file_map = {}
    start_node = [node for node, degree in process_graph.in_degree() if degree == 0][0]
    dfs_edges = list(nx.dfs_edges(process_graph,source=start_node))
    parent_process_id = dfs_edges[0][0][0]
    process_file_map[f"{project_root}/flake.lock".encode()] = parent_process_id
    process_file_map[f"{project_root}/flake.nix".encode()] = parent_process_id
    check_for_clone_and_open(dfs_edges, process_tree_prov_log, 1, process_file_map, paths)

def test_bash_in_bash_pipe() -> None:
    command = ["bash", "-c", f"head {project_root}/flake.nix | tail"]
    process_tree_prov_log = execute_command(command)
    process_graph = analysis.provlog_to_digraph(process_tree_prov_log)
    assert not analysis.validate_hb_graph(process_tree_prov_log, process_graph)
    paths = [f'{project_root}/flake.nix'.encode(), b'stdout']
    start_node = [node for node, degree in process_graph.in_degree() if degree == 0][0]
    dfs_edges = list(nx.dfs_edges(process_graph,source=start_node))
    check_for_clone_and_open(dfs_edges, process_tree_prov_log, len(paths), {}, paths)


def test_pthreads() -> None:
    process_tree_prov_log = execute_command([f"{project_root}/probe_src/tests/c/createFile.exe"])
    process_graph = analysis.provlog_to_digraph(process_tree_prov_log)
    assert not analysis.validate_hb_graph(process_tree_prov_log, process_graph)
    root_node = [n for n in process_graph.nodes() if process_graph.out_degree(n) > 0 and process_graph.in_degree(n) == 0][0]
    bfs_nodes = [node for layer in nx.bfs_layers(process_graph, root_node) for node in layer]
    root_node = [n for n in process_graph.nodes() if process_graph.out_degree(n) > 0 and process_graph.in_degree(n) == 0][0]
    dfs_edges = list(nx.dfs_edges(process_graph,source=root_node))
    total_pthreads = 3
    paths = [b'/tmp/0.txt', b'/tmp/1.txt', b'/tmp/2.txt']
    check_pthread_graph(bfs_nodes, dfs_edges, process_tree_prov_log, total_pthreads, paths)
    
def execute_command(command: list[str], return_code: int = 0) -> ProvLog:
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
    process_tree_prov_log = parse_probe_log(input)
    return process_tree_prov_log


def check_for_clone_and_open(
        dfs_edges: typing.Sequence[tuple[Node, Node]],
        process_tree_prov_log: ProvLog,
        number_of_child_process: int,
        process_file_map: dict[bytes, int],
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
        
        curr_node_op = get_op_from_provlog(process_tree_prov_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if curr_node_op is not None:
            curr_node_op_data = curr_node_op.data
        if(isinstance(curr_node_op_data,CloneOp)):
            next_op = get_op_from_provlog(process_tree_prov_log, edge[1][0], edge[1][1], edge[1][2], edge[1][3])
            if next_op is not None:
                next_op_data = next_op.data
            if isinstance(next_op_data,ExecOp):
                assert edge[1][0] == curr_node_op_data.task_id
                check_child_processes.append(curr_node_op_data.task_id)
                continue
            if isinstance(next_op_data,InitProcessOp):
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
                process_file_map[paths[current_child_process-1]] = curr_node_op_data.task_id
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
            fd = curr_node_op_data.low_fd
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
            next_init_op = get_op_from_provlog(process_tree_prov_log,curr_pid,1,curr_pid,0)
            if next_init_op is not None:
                next_init_op_data = next_init_op.data
                assert isinstance(next_init_op_data, InitExecEpochOp)
            if next_init_op_data.program_name == b'tail':
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
        process_tree_prov_log: ProvLog,
        paths: list[bytes],
) -> None:
    reserved_file_descriptors = [0, 1, 2]
    file_descriptors = set[int]()
    for edge in dfs_edges:
        curr_pid, curr_epoch_idx, curr_tid, curr_op_idx = edge[0]
        curr_node_op = get_op_from_provlog(process_tree_prov_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if curr_node_op is not None:
            curr_node_op_data = curr_node_op.data
        if(isinstance(curr_node_op_data,OpenOp)):
            file_descriptors.add(curr_node_op_data.fd)
            path = curr_node_op_data.path.path
            if path in paths:
                paths.remove(path)
        elif(isinstance(curr_node_op_data,CloseOp)):
            fd = curr_node_op_data.low_fd
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
        process_tree_prov_log: ProvLog,
        total_pthreads: int,
        paths: list[bytes],
) -> None:
    check_wait = []
    process_file_map = {}
    current_child_process = 0
    file_descriptors = set[int]()
    reserved_file_descriptors = [1, 2, 3]
    edge = dfs_edges[0]
    parent_pthread_id = get_op_from_provlog(process_tree_prov_log, edge[0][0], edge[0][1], edge[0][2], edge[0][3]).pthread_id

    for edge in dfs_edges:
        curr_pid, curr_epoch_idx, curr_tid, curr_op_idx = edge[0]
        curr_node_op = get_op_from_provlog(process_tree_prov_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
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
        curr_node_op = get_op_from_provlog(process_tree_prov_log, curr_pid, curr_epoch_idx, curr_tid, curr_op_idx)
        if curr_node_op is not None and (isinstance(curr_node_op.data,OpenOp)):
            file_descriptors.add(curr_node_op.data.fd)
            path = curr_node_op.data.path.path
            print("open", curr_tid, curr_node_op.pthread_id, curr_node_op.data.fd)
            if path in paths:
                if len(process_file_map.keys())!=0 and parent_pthread_id!=curr_node_op.pthread_id:
                    # ensure the right cloned process has OpenOp for the path
                    assert process_file_map[path] == curr_node_op.pthread_id
        elif curr_node_op is not None and (isinstance(curr_node_op.data, CloseOp)):
            fd = curr_node_op.data.low_fd
            print("close", curr_tid, curr_node_op.pthread_id, curr_node_op.data.low_fd)
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

def get_op_from_provlog(
        process_tree_prov_log: ProvLog,
        pid: int,
        exec_epoch_id: int,
        tid: int,
        op_idx: int,
) -> Op:
    if op_idx == -1 or exec_epoch_id == -1:
        raise ValueError()
    return process_tree_prov_log.processes[pid].exec_epochs[exec_epoch_id].threads[tid].ops[op_idx]


def test_dataflow_graph_to_nextflow_script() -> None:	
    dataflow_graph = nx.DiGraph()	
    A = FileNode(0, 0, "A.txt")	
    B = FileNode(1, 0, "B.txt")	
    W = ProcessNode(0, ("cp", "A.txt", "B.txt"))	
    dataflow_graph.add_nodes_from([A, B], color="red")	
    dataflow_graph.add_nodes_from([W], color="blue")	
    dataflow_graph.add_edges_from([(A, W), (W, B)])	

    expected_script = '''nextflow.enable.dsl=2



process process_140080913286064 {
    input:
    path "A.txt"
   

    output:
    path "B.txt"
   

    script:
    """
    cp A.txt B.txt
    """
}

workflow {

  A_2etxt_20v0=file("A.txt")
  B_2etxt_20v0=file("B.txt")
  B_2etxt_20v0 = process_140080913286064(A_2etxt_20v0)
}'''	
    generator = NextflowGenerator(dataflow_graph)
    script = generator.generate_workflow()

    script = re.sub(r'process_\d+', 'process_*', script)
    expected_script = re.sub(r'process_\d+', 'process_*', expected_script)

    assert script == expected_script	

    A = FileNode(0, 0, "A.txt")	
    B0 = FileNode(1, 0, "B.txt")	
    B1 = FileNode(1, 1, "B.txt")	
    C = FileNode(3, 0, "C.txt")	
    W = ProcessNode(0,("cp", "A.txt", "B.txt"))	
    X = ProcessNode(1,("sed", "s/foo/bar/g", "-i", "B.txt"))	
    # Note, the filename in FileNode will not always appear in the cmd of ProcessNode!	
    Y = ProcessNode(2,("analyze", "-i", "-k"))	


    example_dataflow_graph = nx.DiGraph()	
    # FileNodes will be red and ProcessNodes will be blue in the visualization	
    # Code can distinguish between the two using isinstance(node, ProcessNode) or likewise with FileNode	
    example_dataflow_graph.add_nodes_from([A, B0, B1, C], color="red")	
    example_dataflow_graph.add_nodes_from([W, X, Y], color="blue")	
    example_dataflow_graph.add_edges_from([	
        (A, W),	
        (W, B0),	
        (B0, X),	
        (X, B1),	
        (A, Y),	
        (B1, Y),	
        (Y, C),	
    ])	

    expected_script = '''nextflow.enable.dsl=2



process process_140123042500672 {
    input:
    path "A.txt"
   

    output:
    path "B.txt"
   

    script:
    """
    cp A.txt B.txt
    """
}

process process_140123042498656 {
    input:
    path "B.txt"
   

    output:
    path "B.txt"
   

    script:
    """
    sed s/foo/bar/g -i B.txt
    """
}

process process_140123043038656 {
    input:
    path "A.txt"
    path "B.txt"
   

    output:
    path "C.txt"
   

    script:
    """
    analyze -i -k
    """
}

workflow {

  A_2etxt_20v0=file("A.txt")
  B_2etxt_20v0=file("B.txt")
  B_2etxt_20v0 = process_140123042500672(A_2etxt_20v0)
  B_2etxt_20v1 = process_140123042498656(B_2etxt_20v0)
  C_2etxt_20v0 = process_140123043038656(A_2etxt_20v0, B_2etxt_20v1)
}'''	

    generator = NextflowGenerator(example_dataflow_graph)
    script = generator.generate_workflow()
    script = re.sub(r'process_\d+', 'process_*', script)
    expected_script = re.sub(r'process_\d+', 'process_*', expected_script)
    assert script == expected_script	