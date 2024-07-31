import networkx as nx
import pathlib
import dataclasses
import os
from typing import Tuple, List


## Assuming this is definition of the dataflow graph
@dataclasses.dataclass(frozen=True)
class FileNode:
    inode: int
    version: int
    fileName: str = None

@dataclasses.dataclass(frozen=True)
class ProcessNode:
    cmd: Tuple[str, ...]

def check_file_existence(file_nodes: List[FileNode]) -> List[pathlib.Path]:
    missing_files = []
    for file_node in file_nodes:
        file_path = pathlib.Path(file_node.fileName)
        if not file_path.exists():
            missing_files.append(file_path)
    return missing_files

def create_process_file(process_node: ProcessNode, idx: int, inputs: str, outputs: str, workflow_dir: pathlib.Path):
    process_template = f"""
process process_{idx} {{
    input:
    {inputs}
    
    output:
    {outputs}
    
    script:
    \"\"\"
    {' '.join(process_node.cmd)}
    \"\"\"
}}
"""
    process_file_path = workflow_dir / f'process_{idx}.nf'
    with process_file_path.open('w') as process_file:
        process_file.write(process_template.strip())

def generate_missing_files(file_nodes: List[FileNode], workflow_dir: pathlib.Path):
    for file_node in file_nodes:
        file_path = file_node.fileName
        if not file_path.exists():
            raise FileNotFoundError(f"File {file_node.fileName} does not exist.")

def dataflow_graph_to_nextflow_files(dataflow_graph: nx.DiGraph, workflow_dir: pathlib.Path):
    file_nodes = {node for node in dataflow_graph.nodes if isinstance(node, FileNode)}
    process_nodes = [node for node in dataflow_graph.nodes if isinstance(node, ProcessNode)]
    
    missing_files = check_file_existence(list(file_nodes))
    if missing_files:
        generate_missing_files(list(file_nodes), workflow_dir)

    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_lines = []
    processes = []
    channel_mappings = {}
    for node in file_nodes:
        channel_name = f"ch_{node.inode}_{node.version}"
        channel_mappings[node] = f"Channel.fromPath('{node.fileName}').set {{ {channel_name} }}"
    
    for idx, process_node in enumerate(process_nodes):
        input_channels = []
        output_channels = []
        input_paths = []
        output_paths = []
        for predecessor in dataflow_graph.predecessors(process_node):
            if isinstance(predecessor, FileNode):
                input_channels.append(f"ch_{predecessor.inode}_{predecessor.version}")
                input_paths.append(predecessor.fileName)
        
        for successor in dataflow_graph.successors(process_node):
            if isinstance(successor, FileNode):
                output_channels.append(f"ch_{successor.inode}_{successor.version}")
                output_paths.append(successor.fileName)
        
        inputs = "\n    ".join([f"path {ch}" for ch in input_channels])
        outputs = "\n    ".join([f"path \"{output_paths[i]}\"" for i in range(len(output_channels))])

        create_process_file(process_node, idx, inputs, outputs, workflow_dir)

        process_name = f"process_{idx}"
        if len(input_channels) == 1:
            workflow_lines.append(f"{output_channels[0]} = {process_name}({input_channels[0]})")
        elif len(input_channels) > 1:
            workflow_lines.append(f"{output_channels[0]} = {process_name}({', '.join(input_channels)})")
        else:
            workflow_lines.append(f"{output_channels[0]} = {process_name}()")

        processes.append(f"include {{ {process_name} }} from './{process_name}.nf'")
                              
    channel_definitions = "\n".join(channel_mappings.values())
    workflow_definition = "\n  ".join(workflow_lines)
    processes_definition = "\n".join(processes)
    workflow_script = f"{channel_definitions}\n\n{processes_definition}\n\nworkflow {{\n  {workflow_definition}\n}}\n"

    workflow_file_path = workflow_dir / 'main.nf'
    with workflow_file_path.open('w') as workflow_file:
        workflow_file.write(workflow_script)

def arg_parser():
    import argparse
    parser = argparse.ArgumentParser(description='Generate Nextflow workflow files from a dataflow graph')
    parser.add_argument('graph', type=nx.DiGraph(), help='Path to the graph file')
    parser.add_argument('workflow_dir', type=str, help='Directory where the workflow files will be created')
    return parser.parse_args()

if __name__ == '__main__':
    args = arg_parser()

    dataflow_graph_to_nextflow_files(args.graph, args.workflow_dir)
    print(f"Workflow files generated in {args.workflow_dir}")
