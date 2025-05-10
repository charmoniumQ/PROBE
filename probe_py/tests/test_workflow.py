import numpy
import re
import pytest
import pathlib
import networkx as nx
from probe_py.analysis import FileAccess, ProcessNode, DfGraph
from probe_py.workflows import NextflowGenerator
from probe_py.ptypes import Host, InodeVersion, Inode, Device


tmpdir = pathlib.Path(__file__).resolve().parent.parent / "tmp"


host = Host.localhost()
device = Device(0, 0)
time = numpy.datetime64(0, "ns")
newer_time = numpy.datetime64(1, "ns")


@pytest.mark.xfail
def test_dataflow_graph_to_nextflow_script() -> None:
    a_file_path = tmpdir / "A.txt"
    b_file_path = tmpdir / "B.txt"

    a_file_path.write_text("This is A.txt")
    b_file_path.write_text("This is A.txt")

    dataflow_graph = nx.DiGraph[FileAccess | ProcessNode]()

    A = FileAccess(InodeVersion(Inode(host, device, 0), time, 0), pathlib.Path("A.txt"))
    B = FileAccess(InodeVersion(Inode(host, device, 1), time, 0), pathlib.Path("B.txt"))
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
    generator = NextflowGenerator()
    script = generator.generate_workflow(dataflow_graph)

    script = re.sub(r'process_\d+', 'process_*', script)
    expected_script = re.sub(r'process_\d+', 'process_*', expected_script)
    assert script == expected_script

    A  = FileAccess(InodeVersion(Inode(host, device, 0), time, 0), pathlib.Path("A.txt"))
    B0 = FileAccess(InodeVersion(Inode(host, device, 1), time, 0), pathlib.Path("B.txt"))
    B1 = FileAccess(InodeVersion(Inode(host, device, 1), newer_time, 0), pathlib.Path("B.txt"))
    C  = FileAccess(InodeVersion(Inode(host, device, 3), time, 0), pathlib.Path("C.txt"))
    W = ProcessNode(0,("cp", "A.txt", "B.txt"))
    X = ProcessNode(1,("sed", "s/foo/bar/g", "-i", "B.txt"))
    # Note, the filename in FileNode will not always appear in the cmd of ProcessNode!
    Y = ProcessNode(2,("analyze", "-i", "-k"))


    example_dataflow_graph = DfGraph()
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

    generator = NextflowGenerator()
    script = generator.generate_workflow(example_dataflow_graph)
    script = re.sub(r'process_\d+', 'process_*', script)
    expected_script = re.sub(r'process_\d+', 'process_*', expected_script)
    assert script == expected_script
