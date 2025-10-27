# Developer's README

## Why are all of your git commit messages garbage?

- We've given up on making git commit messages in feature branches meaningful. However, we use PR-based squash-merging. We will give a meaningful message at squash-merge time.

## Principles

- **How to replay old libcalls**:
I don't like replaying libcalls by intercepting and copy/pasting contents of the previous invocation (what RR-debugger does). That approach either disallows "new" executions in the "old" environment OR it can have inconsistencies if the same data is accessed by an un-recorded libcall. New execution is really important for scientific reproducibility. If the only goal was to replay "old" execution (no "new"), just send them a tar of the touched files and stdout. One often wants to change/tweak something, new data, different program path, whatnot.

  I prefer to replay libcalls by changing the system such that the result of the previous invocation is the "right answer". E.g., Rather than intercept read libcalls to give the old data, run the process in a container where the file actually has the old data. New executions will work natively.

## Glossary





- **libprobe** (our program): uses `$LD_PRELOAD` to hook library calls that invoke prov ops (see the implementation at [`./probe_src/libprobe`](./probe_src/libprobe)). It saves a record specifying the input or output for later analysis. Depending on a runtime option, it will save the original file contents (slow but replayable) or just the name of the original file (fast but not replayable). Libprobe uses a [memory-mapped](https://www.wikiwand.com/en/Memory-mapped_file) [arena allocator](https://www.wikiwand.com/en/Region-based_memory_management) to log records to disk at high speeds (see the implementation at [`./probe_src/arena/README.md`](./probe_src/arena/README.md)).

- **Exec epoch** (our term): the [exec-family](https://www.man7.org/linux/man-pages/man3/exec.3.html) of syscalls replace the _current_ process by loading a new one. The period in between subsequent execs or between an exec and an exit is called an "exec epoch". Note that we consider the thread's lifetime to be a sub-interval of the exec epoch (each exec epochs contains threads), since a call to `exec` kills all threads (Linux considers the main thread as killed and re-spawned at the exec boundary, even though it has the same PID and TID).

- **PROBE log** (our output): A tar archive of logs for each process, for each exec epoch, for each thread spawned during that exec epoch. Each log contains an ordered list of prov ops.

- **PROBE record** (our IR): An unstable intermediate representation of the data in a probe log (see the [section on serialization formats](https://github.com/charmoniumQ/PROBE/blob/main/probe_src/probe_frontend/README.md#serialization-formats) for more details).

- **Transcription** (our term): The process of converting a PROBE record to a PROBE log.

- **Translation**  (joke): The process of polypeptide synthesis from mRNA strands generated during [**transcription**](https://en.wikipedia.org/wiki/Transcription_(biology)).

- **Program order** (our adaptation of an existing term): is a [partial order](https://www.wikiwand.com/en/Partially_ordered_set) on the set of prov ops, which is the order the operations appear in a dynamic trace of a single thread.

- **Process fork-join order** (our term): is a partial order on the set of prov ops, which is that if A forks B, then the `fork` prov op in A should precede the first prov op of B. Likewise if A calls `waitpid` and `waitpid` returns the PID of B, then the last prov op in B should precede completion of the prov op `waitpid` in A.

- **Happens-before order** (our term of an [existing term](https://www.wikiwand.com/en/Happens-before)): is the union of program order and process fork-join order.

  - If a write from global state happens-before a read to global state, then the information _may_ flow from the write to the read.
  - If a read happens-before a write, information _can't_ flow from the write to the read.
  - If neither is true, information _may_ flow.

- **Prov op interval** (our term): is an pair of prov ups, one called "upper" the other called "lower", where the upper precedes the lower in happens-before order. We say "x is in the interval" for a prov op x, if the upper prov op happens-before x and x happens-before the lower prov op.

- **Open/close interval** (our term): is a prov op interval between the `open` of a file and its associated `close`. We think it would be too expensive to track individual file reads and writes. Therefore, we track the opens and closes instead. Any prov op in that interval may read or write that file, depending on the open mode. Although we lose specificity by tracking open/close intervals instead of reads/writes, our hypothesis is that correct programs will often separate their reads from their writes by process fork-join order.

  E.g., suppose `foo` and `bar` are some black-box executables. We don't know how to interpret their shell arguments. Suppose they are composed in a shell script like `foo && bar`, which we run with PROBE. We would get the following PROBE log (very roughly):

# Python package

probe_py is a package that implements experimental, non-core CLI functions of PROBE and Python library functionality of PROBE.

Required reading: <https://matt.sh/python-project-structure-2024>
