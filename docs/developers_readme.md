# Developer's README

## Principles

- **How to replay old libcalls**:
I don't like replaying libcalls by intercepting and copy/pasting contents of the previous invocation (what RR-debugger does). That approach either disallows "new" executions in the "old" environment OR it can have inconsistencies if the same data is accessed by an un-recorded libcall. New execution is really important for scientific reproducibility. If the only goal was to replay "old" execution (no "new"), just send them a tar of the touched files and stdout. One often wants to change/tweak something, new data, different program path, whatnot.

  I prefer to replay libcalls by changing the system such that the result of the previous invocation is the "right answer". E.g., Rather than intercept read libcalls to give the old data, run the process in a container where the file actually has the old data. New executions will work natively.

## Glossary

- **Executable**: An executable is a file that contains the information telling a operating system and computer hardware how to execute a specific task. In paarticular, they instruct the operating system to load certain hardware instructions and data to certain locations in memory. In Linux, they are specified using the [ELF format](https://www.wikiwand.com/en/Elf_format).

- **Loader**: A part of the operating system which loads the instructions and data specified by an executable file into memory. In Linux, the loader is called [`ld.so`](https://www.man7.org/linux/man-pages/man8/ld.so.8.html).

- **Shared library**: A file containing a mapping from symbols to data or instructions. An executable can request a certain shared library be loaded at a certain place. The shared library can be specified by absolute path or by relative path, which will be resolved according to specific rules (see `RPATH` in [`man ld.so`](https://www.man7.org/linux/man-pages/man8/ld.so.8.html)).

- **Libc**: A shared library that implements the functions defined in ANSI C. "In theory", the syscall table is the interface between an OS and an application; the OS provides `open` at syscall `SYS_OPEN`. "In practice", libc is the interface between the OS and an applications; the OS's libc will define `FILE* fopen(const char* filename, const char* mode)`. This is because the syscall table has limited slots and expensive to invoke. Splitting paths is certainly OS dependent, but OS designers don't want to waste a valuable syscall slot for something that can be done in userspace, so they put it in libc. GNU Libc (aka glibc) is the most common implementation of Libc on Linux. The principle of using libc as an interface is quite strong; Rust uses static (not shared) libraries for everything _except_ libc, because it is the best way to interface the OS. There are some notable exceptions, however; Go language does not use dynamically link against libc. Those programs are opaque to PROBE until future work, which may involve binary rewriting or ptrace.

- **Symbol**: A symbol is a string used as the name of a global variable or function, optionally with version information appended to it, e.g., `fopen@@GLIBC_2.2.5`. Shared library exports symbols that can be referenced from an executable.

- **Library interposition** is a technique that replaces a function symbol in a common library, like Libc, with a "proxy symbol". The proxy symbol will usually find and call the "true symbol" in the underlying library, but it may do arbitrary filtering, logging, or pre/post-processing as well. The proxy symbol is said to "hook" or "override" the original symbol. Library interposition is described more in [Curry's 1994 USENIX paper on library interposition in System V](https://www.usenix.org/conference/usenix-summer-1994-technical-conference/profiling-and-tracing-dynamic-library-usage), although it was probably known before that.

- **`$LD_PRELOAD`**: an environment variable that tells the loader to load the colon-delimited list of shared libraries _before_ loading the other shared libraries that the program requests. These libraries will get searched first when the program requests a certain symbol. One can use `$LD_PRELOAD` to implement library interpositioning on Linux.

- **Provenance**: the process by which a particular element of the system's global state (often a file) came to have its current value. The process often includes an executable, its arguments, its environments, the files it read, and the provenance of the executable and read-files. We can observe some provenance by tracing one process, but most of the benefits are conferred by tracing a _set_ of interacting processes, e.g., a shell script, Makefile, or workflow.

- **Provenance operation** (our term, also called "prov op"): an operation that reads or writes global state. Often the global state is a file in the filesystem, but it can also be calling for the current time, calling for an OS-level pseudo-random number (i.e., `getrand`), forking a process, or waiting on a process. If we observe all provenance operations relating to a specific element, we can infer the provenance of that element.

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

  - PID 100:
    - Exec `bash`
    - Fork (returns 101)
    - Waitpid 101
    - Fork (returns 102)
    - Waitpid 102
  - PID 101:
    - Exec `foo`
    - Open `input_file` for reading
    - Open `temp_file` for writing
    - (many reads and writes happen, which we do not track)
    - Close all files
  - PID 102:
    - Exec `bar`
    - Open `output_file` for writing
    - Open `temp_file` for reading
    - (many reads and writes happen, which we do not track)
    - Close all files

  The entire close of `temp_file` in PID 101 precedes waitpid 101 in fork-join order, waitpid 101 precedes fork 102 in program order, and fork 102 precedess the open of `temp_file` in PID 102, so we can conclude that information may flow from `foo` to `bar`.

  From which, we can deduce the provenance graph `input_file` -> `foo` -> `temp_file` -> `bar` -> `output_file` with only the open/close intervals and happens-before order.

# Python package

probe_py is a package that implements experimental, non-core CLI functions of PROBE and Python library functionality of PROBE.

Required reading: <https://matt.sh/python-project-structure-2024>
