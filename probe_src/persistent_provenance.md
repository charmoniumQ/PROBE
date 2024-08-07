`probe_py.manual.persistent_provenance` implements persistent (between-process) provenance.

`probe record ...` efficiently trackes provenance within a single process, writing the result to `probe_log`.
If the process which reads a file is not the same as the process which writes one, but they have a common ancestor parent, this works well.
For example, suppose a compiler reads `main.c` and writes `main.o`, and a linker reads `main.o` and writes `main.a`.
- PROBEing just the compiler will not capture the full usage of the .c files;
- PROBEing just the linker will not capture the full source of the .a files;
- However PROBEing the make which invokes both (make is a common ancestor) sufficiently captures the sources and uses of all the files involved.

However, there are cases where there is not a common ancestor process:
- The computation could be could be a multi-node (a process on machine A and process on machine B have no common ancestor).
- The computation could be carried out between restarts (process writes file, restart machine, process reads file).

Therefore, we will write provenance persistently to disk in a data directory (in [XDG data
home](https://wiki.archlinux.org/title/XDG_Base_Directory)) at transcription-time.

When we PROBE a process, we learn which InodeVersions got produced, which got used, and other necessary conditions for the process to execute.
This data will constitute the Process object.

PROBE already constructs "within process-and-its-children" dataflow graph, but with the stored provenance data, we can imagine the "between processes" dataflow graph.
The common InodeVersions between processes should get "linked up".

One common query is: "what inputs got used to generate this InodeVersion?".
The queries navigate the between-process dataflow DAG opposite the direction of information flow.
Therefore, we need to make this operation fast.
Scanning through every Process object will be too tedious, since ever process the user ever PROBEd will have a corresponding Process object.

To speed up queries, we will have an index mapping from InodeVersions to the Processes that produced it.
In our data directory, there will be these flat subdirectories: `inode_version_writes`, and `processes`.
Flat directories can be thought of as key-value stores, where the filename is the key.
- `inode_version_writes` maps an inode-and-version (filename) to the process ID (in the file contents) of the process that created it.
- `processes` maps a process ID (filename) to a Process object (in the file contents).

Note: multi-process sqlite is either not performant (globally lock entire database) or not easy (lock each row somehow), but filesystem will work fine for our case, since we just need a key-value store.
