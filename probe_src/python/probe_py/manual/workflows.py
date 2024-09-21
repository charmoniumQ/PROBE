from probe_py.manual.analysis import ProcessNode, FileNode
import networkx as nx
import abc
from typing import List, Set
import pathlib

"""
All the cases we should take care of:
1- One Input, One Output
2- One Input, Multiple Outputs
3- Multiple Inputs, One Output
4- Multiple Inputs, Multiple Outputs
5- Chained Commands: Inline commands that directly modify the input file (e.g., using sed, awk, or similar) 
6- No Input Command: Commands like ls .: Commands that don't take an explicit input file but generate output 
7- Ensure that any environment variables or context-specific settings are captured and translated into the Nextflow environment
8- File and Directory Structure Assumptions (Scripts that assume a specific directory structure, Commands that change the working directory (cd))
...
"""
class WorkflowGenerator(abc.ABC):
    @abc.abstractmethod
    def generate_workflow(self, graph: nx.DiGraph) -> str:
        pass

class NextflowGenerator(WorkflowGenerator):
    def __init__(self) -> None:
        self.visited: Set[ProcessNode] = set()
        self.process_counter: dict[ProcessNode, int] = {} 
        self.nextflow_script: list[str] = []  
        self.workflow: list[str] = []

    def escape_filename_for_nextflow(self, filename: str) -> str:
        """
        Escape special characters in a filename for Nextflow.
        Replace any non-letter, non-number character with _i, where i is the ASCII character code in hex.
        Additionally, escape underscores and prepend an escape code if the filename starts with a number.
        """
        escaped_filename = []

        for char in filename:
            if char.isalnum():  # Keep letters and numbers unchanged
                escaped_filename.append(char)
            else:  # Replace other characters with their ASCII code in hex
                escaped_filename.append(f'_{ord(char):02x}')

        # Ensure the filename doesn't start with a number by prepending an escape code
        if escaped_filename and escaped_filename[0].isdigit():
            escaped_filename.insert(0, '_num_')

        return ''.join(escaped_filename)


    def handle_standard_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> str:
        input_files = " ".join([f'path "{file.file}"\n   ' for file in inputs])
        output_files = " ".join([f'path "{file.file}"\n   ' for file in outputs])
        
        return f"""
process process_{id(process)} {{
    input:
    {input_files}

    output:
    {output_files}

    script:
    \"\"\"
    {' '.join(process.cmd)}
    \"\"\"
}}"""

    def handle_dynamic_filenames(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> str:
        input_files = " ".join([f'path "{file.file}"\n   ' for file in inputs])
        output_files = " ".join([f'path "{file.file}"\n   ' for file in outputs if file.file])

        return f"""
process process_{id(process)} {{
    input:
    {input_files}

    output:
    {output_files}

    script:
    \"\"\"
    {' '.join(process.cmd)}
    \"\"\"
}}"""

    def handle_parallel_execution(self, process: ProcessNode) -> str:
        input_files = "splitFile"
        output_files = "outputFile"
        return f"""
process process_{id(process)} {{
    input:
    "{input_files}"

    output:
    "{output_files}"

    script:
    \"\"\"
    {' '.join(process.cmd)}
    \"\"\"
}}
splitFile = Channel.fromPath('inputFiles/*').splitText()
process_{id(process)} (splitFile.collect())"""

    def handle_custom_shells(self, process: ProcessNode) -> str:
        return f"""
process process_{id(process)} {{
    output:
        stdout
    
    script:
    \"\"\"
    {' '.join(process.cmd)}
    \"\"\"
}}"""



    def is_standard_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> bool:
        return len(inputs) >= 1 and len(outputs) == 1

    def is_multiple_output_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> bool:
        return len(inputs) >= 1 and len(outputs) >= 1
    
    def is_dynamic_filename_case(self, process: ProcessNode, outputs: List[FileNode]) -> bool:
        return any("*" in file.file or "v*" in file.file for file in outputs if file.file)

    def is_parallel_execution(self, process: ProcessNode) -> bool:
        return len(process.cmd) > 1 and "parallel" in process.cmd

    def create_processes(self) -> None:
        """
        Create Nextflow processes based on the dataflow graph.
        """
        for node in self.graph.nodes:
            if isinstance(node, ProcessNode) and node not in self.visited:
                inputs = [n for n in self.graph.predecessors(node) if isinstance(n, FileNode)]
                outputs = [n for n in self.graph.successors(node) if isinstance(n, FileNode)]

                if self.is_standard_case(node, inputs, outputs) :
                    process_script = self.handle_standard_case(node, inputs, outputs)
                    self.nextflow_script.append(process_script)
                    self.workflow.append(f"{self.escape_filename_for_nextflow(outputs[0].label)} = process_{id(node)}({', '.join([self.escape_filename_for_nextflow(i.label) for i in inputs])})")
                elif self.is_multiple_output_case(node,inputs,outputs) : 
                    raise NotImplementedError("Handling multiple outputs not implemented yet.")
                elif self.is_dynamic_filename_case(node, outputs):
                    process_script = self.handle_dynamic_filenames(node, inputs, outputs)
                elif self.is_parallel_execution(node):
                    process_script = self.handle_parallel_execution(node)
                else:
                    process_script = self.handle_custom_shells(node)
                    self.nextflow_script.append(process_script)
                    self.workflow.append(f"process_{id(node)}()")

                self.visited.add(node)
  
    def generate_workflow(self, graph: nx.DiGraph) -> str:  
        """
        Generate the complete Nextflow workflow script from the graph.
        """
        self.graph = graph
        self.nextflow_script.append("nextflow.enable.dsl=2\n\n")
        self.create_processes()

        # Append the workflow section
        self.nextflow_script.append("\nworkflow {\n")

        # Add file nodes to the script
        filenames = set()
        for node in self.graph.nodes:
            if isinstance(node, FileNode):
                escaped_name = self.escape_filename_for_nextflow(node.label)
                if node.inodeOnDevice not in filenames:
                    if pathlib.Path(node.file).exists():
                        self.nextflow_script.append(f"  {escaped_name}=file(\"{node.file}\")")
                        filenames.add(node.inodeOnDevice)

        
        for step in self.workflow:
            self.nextflow_script.append(f"  {step}")
        self.nextflow_script.append("}")

        return "\n".join(self.nextflow_script)


class MakefileGenerator:
    def __init__(self):
        self.visited: Set[ProcessNode] = set()
        self.makefile_rules: list[str] = []

    def escape_filename_for_makefile(self, filename: str) -> str:
        """
        Escape special characters in a filename for Makefile.
        Replace spaces with underscores and other special characters with underscores as well.
        """
        return filename.replace(" ", "_").replace("(", "_").replace(")", "_").replace(",", "_")

    def handle_standard_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> str:
        input_files = " ".join([self.escape_filename_for_makefile(file.label) for file in inputs])
        output_files = " ".join([self.escape_filename_for_makefile(file.label) for file in outputs])
        cmd = " ".join(process.cmd)
        
        return f"{output_files}: {input_files}\n\t{cmd}\n"

    def handle_dynamic_filenames(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> str:
        input_files = " ".join([self.escape_filename_for_makefile(file.label) for file in inputs])
        output_files = " ".join([self.escape_filename_for_makefile(file.file) + "_v*" for file in outputs if file.file])
        cmd = " ".join(process.cmd)
        
        return f"{output_files}: {input_files}\n\t{cmd}\n"

    def handle_parallel_execution(self, process: ProcessNode) -> str:
        input_files = "splitFile"
        output_files = "outputFile"
        cmd = " ".join(process.cmd)

        return f"{output_files}: {input_files}\n\t{cmd} &\n"

    def handle_custom_shells(self, process: ProcessNode) -> str:
        cmd = " ".join(process.cmd)
        
        return f".PHONY: process_{id(process)}\nprocess_{id(process)}:\n\t{cmd}\n"

    def is_standard_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> bool:
        return len(inputs) >= 1 and len(outputs) == 1

    def is_multiple_output_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> bool:
        return len(inputs) >= 1 and len(outputs) >= 1

    def is_dynamic_filename_case(self, process: ProcessNode, outputs: List[FileNode]) -> bool:
        return any("*" in file.file or "v*" in file.file for file in outputs if file.file)

    def is_parallel_execution(self, process: ProcessNode) -> bool:
        return len(process.cmd) > 1 and "parallel" in process.cmd

    def create_rules(self) -> None:
        """
        Create Makefile rules based on the dataflow graph.
        """
        raise NotImplementedError("Exporting to makefile is not implemented yet.")

    def generate_makefile(self, graph: nx.DiGraph) -> str:
        """
        Generate the complete Makefile script from the graph.
        """
        self.graph = graph
        self.create_rules()
        return "\n".join(self.makefile_rules)