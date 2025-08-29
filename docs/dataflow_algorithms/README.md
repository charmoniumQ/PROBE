# Overview

We have a happens-before graph, A->B means A happens-before B, which is the union of program-order, forks, and joins.

How to construct a dataflow graph?

Certainly program-order and forks have dataflow, carrying an entire copy of the process's memory. Joins are also dataflow, as they carry a return integer. While the integer may not seem like much, often its success or failure (non-zero-ness) is really important for the parent's control flow.

How to version repeated accesses to the same inode?

# Sample-schedule

Pick a "sample" schedule that is a topological order of the hb-graph.

[at_open_algo.py](./at_open_algo.py)

[at_opens_and_closes.py](./at_opens_and_closes.py)

[at_opens_and_closes_with_separate_access.py](./at_opens_and_closes_with_separate_access.py)

Problem with event-based: no individual schedule constructs a sufficiently conservative DFG. Consider the following HB graph

digraph {
  Read of A -> Write of B
  Read of B -> Write of A
}

Any valid schedule will only have one inode dataflow edge. But data could flow from second op of second proc to first op of first proc AND from second of first to first of second. Just not in the same schedule.

It doesn't handle `sh -c "a | b"` elegantly, which has the following graph

digraph {
  open pipe for reading -> open pipe for writing -> fork writer -> fork reader -> wait writer -> wait reader -> close pipe for reading -> close pipe for writing;
  fork writer -> close pipe for reading -> dup pipe for writing to stdout -> close pipe for writing -> exec -> wait writer;
  fork reader -> close pipe for writing -> dup pipe for reading to stdin -> close pipe for reading -> exec -> wait reader;
}

A schedule that puts `write` at the close and `read` at the open will not see dataflow from the writing process to the reading one.

# Interval approach

Instead, we take the more complex, "interval" approach.

[interval_algo.py](./interval_algo.py)

[interval_redux.py](./interval_redux.py)

Find the intervals in which a write could have taken place. An interval is for each process, the earliest and latest possible quad in which a read/write may happen.

The logic in `interval_redux.py` for dealing with concurrent segments works if the segments are disjoint.

# Doubts

- Matching closes with opens in thread-level parallelism
  - Global fd table
    - How to when clone and CLONE_FILES?
    - Kernel already implements a readers/writers lock around the fd table https://docs.kernel.org/filesystems/files.html
- TOC2TOU errors with stat->open or stat->close?
  - Change stat->open to open->stat
    - But I still need to check the inode table, to see if I need to copy a file,
      - But only if the file exists and the open mode is truncate
- Chdir with thread-level parallelism
  - Always stat dirfd OR only do stat on fds OR have a global fd table

1. Gate this feature with an env var, so its performance can be evaluated.
   - See copy-files.
   - Since PROBE has both modes, analysis in `probe_py` should support both modes.
2. Have a process-global fd table, maps FDs to open-number. Open-number increments every open and gets logged with the open.
   - Use a multi-level table.
   - Consider 10-bit x 10-bit = 20-bit table at first.
   - If a returned FD is too large, error out loudly.
   - Use readers/writers lock or atomics
   - open-number should go in the Path struct.
3. Uses of the FD, as a dirfd too, or in close, get logged.
   - Accesses with `AT_FDCWD` log the open-number of the cwd.
4. When we reconstruct close,dup,fcntl -> open, we use the open number, if present, otherwise inode-match (current strat).
   - Kill the existing stat in close,dup,fcntl, other fns that operate on FDs.
   - Perhaps `create_path_lazy` should not do a stat when open-number is present.
5. When reconstructing the process-global cwd, we use the open number.
6. Fail loudly on clone if `CLONE_FILES` is set/not-set (whichever poses a problem for us).

Next PR:
7. Two bloom filters for all open-numbers read-from and written-to in this process.
  - a bloom filter query returns either "possibly in set" or "definitely not in set"
  - For each read/write, update filter
  - Open-number is more precise than inode, since the same inode can be opened for multiple periods within the process.
  - Read-from, written-to status gets logged on close.
8. Dataflow can ignore write segments from threads that don't do any writing, read segments from threads that don't do any reading.

# Shell ambiguity

- Dataflow graph of `sh -c 'a | b'` appears to have more edges than it needs, but these edges are necessary because for each edge, there exists a program with the same HB graph that has those edges.
  - The following program is, for our purposes, equivalent to `sh -c '/bin/echo hi | cat'`. Note that uncommenting either pair read1+write1 or read2+write2 creates a dataflow edge from the first_child->parent or parent->first_child, respectively. In practice, we know that there are no such extraneous reads/writes in Bash, but for an arbitrary black-box program, we wouldn't know. Indeed, if we used `echo` instead of `/bin/echo` which invokes a shell builtin rather than a subprocess, then the first fork would have a Write 2 uncommented (with dup2 and execl removed). Really, we should be tracking the reads and writes to resolve the ambiguity more precisely.
  ```
  void main() {
    int pipe_fds[2];
    pipe(pipe_fds);
    pid_t first_fork = fork()
    if (first_fork == 0) {
      // first child
      //read(pipe_fds[0], ...); /* Read 1 */
      //write(pipe_fds[1], ...); /* Write 2 */
      close(pipe_fds[0]);
      dup2(pipe_fds[1], stdout_fileno);
      close(pipe_fds[1]);
      // Exec never returns; it switches to the main method of echo.
      execl("/bin/echo", "hi");
    } else {
      // parent
      //write(pipe_fds[1], ....); /* Write 1 */
      //read(pipe_fds[0], ...); /* Read 2 */
      close(pipe_fds[1]);
      pid_t second_fork = fork();
      if (second_fork) {
        // second child
        dup2(pipe_fds[0], stdin_fileno);
        close(pipe_fds[0]);
        execl("cat");
      } else {
        // parent
        close(pipe_fds[0]);
        wait(first_fork);
        wait(second_fork);
      }
    }
  }
  ```

# Alternatives

ReproZip is incorrect in the following cases:

``` bash
cd ../../benchmark

nix build .#reprozip-all && export PATH="$PWD/result/bin:$PATH" && reprounzip usage_report --disable

# Graph should show a dataflow path from cat to head.
touch src && reprozip trace --overwrite bash -c 'cat src | head' && rm dataflow-graph.dot ; reprounzip graph --dir .reprozip-trace dataflow-graph.dot && xdot dataflow-graph.dot

# Test with a symlink (hardlink is also not supported)
setup="echo hello > src && echo hello > src && rm dst ; ln --symbolic src dst"
cmd="cat src src > tmp && cat tmp > dst"
test="cat dst"
bash -c "$setup"
bash -c "$cmd"
bash -c "$test"
bash -c "$setup" && reprozip trace --overwrite bash -c "$cmd"
# Get trace
rm test-trace.rpz ; reprozip pack test-trace.rpz
# Show files should have src as an input and an output
reprounzip showfiles test-trace.rpz
# Show dataflow
rm dataflow-graph.dot ; reprounzip graph --dir .reprozip-trace dataflow-graph.dot && xdot dataflow-graph.dot

# Same procedure, but with a file that modifies itself
echo hi > src && reprozip trace --overwrite bash -c "cat src src > tmp ; head tmp > src"
rm test-trace.rpz ; reprozip pack test-trace.rpz
# src should be an input file; tmp should not be an input file
reprounzip showfiles test-trace.rpz
rm dataflow-graph.dot ; reprounzip graph --dir .reprozip-trace dataflow-graph.dot && xdot dataflow-graph.dot
# src should have one hello not two.
rm --recursive --force tmpdir && reprounzip directory setup test-trace.rpz tmpdir
```
