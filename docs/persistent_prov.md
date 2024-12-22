`persistent_provenance.py` implements persistent (between-process) provenance.

`probe record ...` efficiently tracks provenance within a single process, writing the result to `probe_log`.
If the process which reads a file is not the same as the process which writes one, but they have a common ancestor parent, this works well.
For example, suppose a compiler reads `main.c` and writes `main.o`, and a linker reads `main.o` and writes `main.a`.
- PROBEing just the compiler will not capture the full usage of the .c files;
- PROBEing just the linker will not capture the full source of the .a files;
- However PROBEing the make which invokes both (make is a common ancestor) sufficiently captures the sources and uses of all the files involved.

However, there are cases where there is not a common ancestor process:
- The computation could be could be a multi-node (a process on machine A and process on machine B have no common ancestor).
- The computation could be carried out between restarts (process writes file, restart machine, process reads file).

Therefore, we will write the dataflow DAG to disk in [XDG data home](https://wiki.archlinux.org/title/XDG_Base_Directory) at transcription-time.
The result is a gigantic dataflow DAG that can span multiple invocations of PROBE, multiple boots, and perhaps even operations on multiple hosts.
If we ran `gcc` on remote `X` and `scp`ed the result back, those could all appear as nodes in the DAG.

Common queries:
- Upward (direction of dataflow) queries:
  - What outputs were dependent on this input? (aka push-based updating). If a user overwrites a particular data file, they may want to regenerate every currently extant output which depended on that data file.
- Downward (opposite of dataflow) queries:
  - What inputs were used to make this output? (aka pull-based updating). This query is used in applications like "Make-without-Makefile" application.
  - When the user does an SCP or Rsync, extract the "relevant" bits of provenance to the remote, so a user at the destination-machine (destination could be local or remote) can query the provenance of the files we are sending.

We need to be able to query the graph in both directions.

While a graph database would be more efficient, sqlite is very battle-tested and does not require a daemon process.
