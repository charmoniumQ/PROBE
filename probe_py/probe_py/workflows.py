from probe_py.analysis import ProcessNode, FileNode
import networkx as nx # type: ignore
import abc
from typing import List, Set, Optional
import pathlib
import shutil
import os
import tempfile
import subprocess
from filecmp import cmp
import re
"""
All the cases we should take care of:
1- One Input, One Output [x]
2- One Input, Multiple Outputs
3- Multiple Inputs, One Output
4- Multiple Inputs, Multiple Outputs
5- Inline Commands: Inline commands that directly modify the input file (e.g., using sed, awk, or similar) [x]
6- Chained Commands: If a process node calls another script [x]
7- No Input Command: Commands like `ls .`: Commands that don't take an explicit input file but generate output [x]
8- Ensure that any environment variables or context-specific settings are captured and translated into the Nextflow environment
9- File and Directory Structure Assumptions (Scripts that assume a specific directory structure, Commands that change the working directory (cd))
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



    def handle_inline_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> str:
        input_files = " ".join([f'path "{os.path.basename(file.file)}"' for file in inputs])
        output_files = " ".join(
            [f'path "{os.path.splitext(os.path.basename(file.file))[0]}_modified{os.path.splitext(file.file)[1]}"' for
             file in inputs])

        # Build inline commands for each file to perform copy, edit, and rename steps
        script_commands = []
        for file in inputs:
            base_name = os.path.basename(file.file)
            temp_name = f"temp_{base_name}"
            final_name = f"{os.path.splitext(base_name)[0]}_modified{os.path.splitext(base_name)[1]}"

            # Replace the original filename in the command with the temp filename
            modified_cmd = []
            for cmd in process.cmd:
                # Substitute all occurrences of the original filename in each command
                cmd_modified = re.sub(r"/(?:[a-zA-Z0-9_\-./]+/)*([a-zA-Z0-9_\-]+\.txt)", temp_name, cmd)
                modified_cmd.append(cmd_modified)

            script_commands.extend([
                f'cp {file.file} {temp_name}',  # Copy to temp file
                " ".join(modified_cmd),  # Apply inline edit with temp filename
                f'mv {temp_name} {final_name}'  # Rename temp file to final output
            ])

        # Join script commands with newline and indentation for Nextflow process
        script_block = "\n    ".join(script_commands)

        # Create the Nextflow process block
        return f"""
process process_{id(process)} {{
    input:
    {input_files}

    output:
    {output_files}

    script:
    \"\"\"
    {script_block}
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

    def is_inline_editing_command_sandbox(self, command: str, input_files: list[FileNode]) -> bool:
        """
        Determine if a command modifies any of the input files in-place, even if the content remains the same.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            sandbox_files = {}

            # Track original modification times and create sandbox files
            original_times = {}
            sandbox_command = command
            for input_file in input_files:
                temp_file = os.path.join(temp_dir, os.path.basename(input_file.file))
                shutil.copy(input_file.file, temp_file)
                sandbox_files[input_file.file] = temp_file

                # Save original modification time
                original_times[input_file.file] = os.path.getmtime(input_file.file)
                sandbox_command = sandbox_command.replace(input_file.file, temp_file)

            # Run the command in the sandbox
            try:
                subprocess.run(sandbox_command, shell=True, check=True)
            except subprocess.CalledProcessError:
                print("Command failed to execute.")
                return False

            # Check if any of the files were modified in-place
            for original_file, sandbox_file in sandbox_files.items():
                # Get the modified time of the sandboxed file after command execution
                sandbox_mod_time = os.path.getmtime(sandbox_file)
                original_mod_time = original_times[original_file]

                # Compare content and modification times
                content_modified = not cmp(original_file, sandbox_file, shallow=False)
                time_modified = sandbox_mod_time != original_mod_time

                # If either the content or modification time has changed, it's an in-place modification
                if content_modified or time_modified:
                    return True

            # Return False if none of the files were modified
            return False

    def is_standard_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> bool:
        return len(inputs) >= 1 and len(outputs) == 1

    def is_inline_case(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> bool:
        return  self.is_inline_editing_command_sandbox(' '.join(process.cmd), inputs)

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

                if self.is_standard_case(node, inputs, outputs):
                    process_script = self.handle_standard_case(node, inputs, outputs)
                    self.nextflow_script.append(process_script)
                    self.workflow.append(f"{self.escape_filename_for_nextflow(outputs[0].label)} = process_{id(node)}({', '.join([self.escape_filename_for_nextflow(i.label) for i in inputs])})")
                elif self.is_multiple_output_case(node,inputs,outputs) : 
                    raise NotImplementedError("Handling multiple outputs not implemented yet.")
                elif self.is_dynamic_filename_case(node, outputs):
                    process_script = self.handle_dynamic_filenames(node, inputs, outputs)
                elif self.is_parallel_execution(node):
                    process_script = self.handle_parallel_execution(node)
                elif  self.is_inline_case(node, inputs, outputs):
                    process_script = self.handle_inline_case(node, inputs, outputs)
                    self.nextflow_script.append(process_script)
                    self.workflow.append(f"process_{id(node)}({', '.join([self.escape_filename_for_nextflow(i.label) for i in inputs])})")
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
    def __init__(self, output_dir: str = "experiments") -> None:
        self.visited: Set[ProcessNode] = set()
        self.makefile_commands: list[str] = []
        self.output_dir = output_dir

    def escape_filename_for_makefile(self, filename: str) -> str:
        """
        Escape special characters in a filename for Makefile.
        Replace spaces and other special characters with underscores.
        """
        return filename.replace(" ", "_").replace("(", "_").replace(")", "_").replace(",", "_")

    def is_hidden_file(self, filename: str) -> bool:
        """
        Determine if a file is hidden.
        Hidden files start with '.' or '._'.
        """
        return filename.startswith('.') or filename.startswith('._')

    def create_experiment_folder_command(self, process: ProcessNode) -> str:
        """
        Generate the command to create a folder for the experiment.
        """
        folder_name = f"process_{id(ProcessNode)}"
        return f"mkdir -p {folder_name}"

    def copy_input_files_command(self, process: ProcessNode, inputs: List[FileNode]) -> Optional[str]:
        """
        Generate the command to copy input files into the experiment folder.
        Returns None if there are no input files.
        """
        if not inputs:
            return None

        folder_name = f"process_{id(ProcessNode)}"
        commands = []
        for file in inputs:
            if self.is_hidden_file(file.label):
                continue  # Skip hidden files
            escaped_file = self.escape_filename_for_makefile(file.label)
            commands.append(f"cp {escaped_file} {folder_name}/")
        
        if commands:
            return "\n\t".join(commands)
        return None

    def run_command_command(self, process: ProcessNode, outputs: List[FileNode]) -> str:
        """
        Generate the command to run the experiment's command within the experiment folder.
        Redirect stdout and stderr to log files if outputs are not files.
        """
        folder_name = f"process_{id(ProcessNode)}"
        cmd = " ".join(process.cmd)
        if not outputs:
            # No output files, redirect to log
            return f"({cmd}) > {folder_name}/output.log 2>&1"
        else:
            # Execute command within the folder
            return f"(cd {folder_name} && {cmd})"

    def handle_process_node(self, process: ProcessNode, inputs: List[FileNode], outputs: List[FileNode]) -> None:
        """
        Generate all necessary Makefile commands for a given process node.
        Handles different cases based on presence of inputs and outputs.
        """
        # Create experiment folder
        self.makefile_commands.append(f"# Process {id(ProcessNode)}: {' '.join(process.cmd)}")
        self.makefile_commands.append(f"\tmkdir -p process_{id(ProcessNode)}")
        
        # Copy input files
        copy_inputs = self.copy_input_files_command(process, inputs)
        if copy_inputs:
            self.makefile_commands.append(f"# Copy input files for process {id(ProcessNode)}")
            self.makefile_commands.append(f"\t{copy_inputs}")
        
        # Run the command
        self.makefile_commands.append(f"# Run command for process {id(ProcessNode)}")
        run_cmd = self.run_command_command(process, outputs)
        self.makefile_commands.append(f"\t{run_cmd}")
        
        # No copying of output files since they are inside the folder

    def create_rules(self) -> None:
        """
        Traverse the graph and create Makefile commands.
        """
        # Ensure the output directory exists
        self.makefile_commands.append(f"\tmkdir -p {self.output_dir}\n")
        
        # Traverse the graph in topological order to respect dependencies
        for node in nx.topological_sort(self.graph):
            if isinstance(node, ProcessNode):
                inputs = [n for n in self.graph.predecessors(node) if isinstance(n, FileNode)]
                outputs = [n for n in self.graph.successors(node) if isinstance(n, FileNode)]
                
                self.handle_process_node(node, inputs, outputs)

    def generate_makefile(self, graph: nx.DiGraph) -> str:
        """
        Generate the complete Makefile script from the graph.
        """
        self.graph = graph
        self.create_rules()
        
        # Assemble the Makefile
        makefile = []
        makefile.append("all:")
        for command in self.makefile_commands:
            # Ensure each command line is properly indented with a tab
            # Makefile syntax requires tabs, not spaces
            makefile.append(f"\t{command}")
        
        return "\n".join(makefile)
