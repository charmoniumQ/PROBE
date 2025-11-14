# Provenance theory

**Provenance** of an attribute of a system's state (often a file) is the following three things:
1. The process by which a particular attribute of the system's global state came to have its current value.
2. The attributes of the system's state which influenced that process.
3. The provenance of those influencing attributes.

"Attribute of a system's state" often refers to "contents of a certain file", but the definition can include the state of a pseudorandom number generator as well.

The "process by which ... came to have its current value" is often a UNIX process, identified by a set of environment variables, an executable, its arguments, its initial current working directory, and its namespace mapping. Initially, we only use the default namespace.

A **provenance operation** (our term, also called "prov op") is an operation that reads or writes global state. Often the global state is a file in the filesystem, but it can also be calling for the current time, calling for an OS-level pseudo-random number (i.e., `getrand`), forking a process, or waiting on a process. If we observe all provenance operations relating to a specific element, we can infer the provenance of that element.

# Library interposition

An **executable** is a file that contains machine code and information needed to execute the machine code in a process, like `python`. On Linux, the executable uses Executable and Linkable Format (ELF). Read more on [Wikipedia](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) or the [man page](https://www.man7.org/linux/man-pages/man5/elf.5.html).

Each executable may not want to include an implementation of `printf`, for many reasons, but the most relevant for us is that the platform is in a better position to implement the function than the **executable**.

For example opening a file (e.g., through `fopen`) involves invoking architecture and OS-specific system calls. For example, `firefox` would rather defer to the platform for how to open a file. Each platform, be it Windows, Linux, MacOS, provides its own platform/architecture-specific implementation of `fopen`.

These implementations are packaged into **shared libraries** (shared between multiple executables on that system). The executable specifies a list of shared libraries, usually identified by filename, and a list of **symbol names** which should be found in one of the specified shared libraries.

The process of finding the shared libraries is called **loading** an executable, and in Linux, the loader is called `ld.so`. `ld.so` has a specific list of places to search for shared libraries, incorporating information specified by the executable, by the environment variables, and by the system. Find more information at the [man page](https://www.man7.org/linux/man-pages/man8/ld.so.8.html).

`probe record <command>` simply runs `<command>` with an `LD_PRELOAD` pointing to `libprobe.so`. `libprobe.so` simply overrides every function in libc that does an executes a provenance operation, e.g., `open()`, `gettimeofday()`, etc.

See [Curry 1994](https://www.usenix.org/conference/usenix-summer-1994-technical-conference/profiling-and-tracing-dynamic-library-usage) for more information on library interposition.

## Example

For example, `hello.c` implements hello world. We can compile an executable, `hello`. Peeking inside the executable with `nm`, we see that `hello` requests the symbol `printf`. `hello` asks for a shared library called `libc.so.6`, which the loader will find at `/lib/x86_64-linux-gnu/libc.so.6`.

```sh
$ echo '
#include <stdio.h>
#include <fcntl.h>
int main() {
  printf("hello world %d\n", open("hello.c", O_RDONLY));
  return 0;
}' > hello.c

$ gcc -Wall -o hello hello.c

$ nm --dynamic hello
...
                 U open
                 U printf

$ ldd hello
        linux-vdso.so.1 (0x00007fdc294d2000)
        libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007fdc292d2000)
        /lib64/ld-linux-x86-64.so.2 (0x00007fdc294d4000)
``` 

However, we can override the default search path by specifying an environment variable called `LD_PRELOAD` as a colon-separated list of libraries to load before the ones that would normally be loaded by `ld.so`. By creating a shared library containing the symbol `printf` and setting `LD_PRELOAD` to point to our library, we can "override" the actual implementation of `printf` visible to the executable. Our implementation can even call the underlying platform's implementation if we elect to.

For example, to override and log calls to `open`, we can write the following:

```sh
$ echo '
#define _GNU_SOURCE
#include <stdio.h>
#include <fcntl.h>
#include <dlfcn.h>
int open(const char *path, int flags, ...) {
  // log attempt
  printf("Open of %s attempted\n", path);

  // get platform''s open
  int (*real_open)(const char*, int, ...);
  real_open = dlsym(RTLD_NEXT, "open");
  // as long as we return real_open(...), the application will see the same value as before.

  // return result of platform''s open
  return real_open(path, flags);
}' > override_open.c

$ gcc -Wall -fpic -shared -ldl -o override_open.so override_open.c

$ LD_PRELOAD=./override_open.so ./hello
Open of hello.c attempted
hello world 3
```

# Path of a lib call

Now that I've explained how library calls can be intercepted, how do they get logged efficiently?

When we intercept a call, such as `open` and `close`, we write a record for each entailed provenance operation in a memory-mapped file. **Memory-mapped file** := method of file I/O that treats the file like a big array of bytes that can be read/written to. In steady-state, writes to the file as fast as a write to a pointer. How fast is writing to a pointer? That depends on the cache, but according to [Norvig's estimates](https://norvig.com/21-days.html#answers), on the order of nanoseconds, almost the fastest a computer can do _anything_.

If the call may overwrite a file that we previously read and the user turned on copy-files-mode, we will copy the file into storage before calling the platform's implementation of the interposed function. This is slow, but necessary to get _ad hoc_ reproducibility for a program that overwrites its input files; there's no way around needing to copy the file.

When the program exits normally, these memory-mapped files are flushed to the disk. If anything, memory-mapped files may slow down program shutdown time slightly; at least all of the writes are naturally "batched". Later on, PROBE will schedule analysis of these files (**analysis phase**).

Each thread has its own, private memory-mapped log, so there are no race conditions and no contention. In the analysis phase, we will have to _stitch_ the thread logs together, to construct a global picture of the program's execution.

## How are files identified

We need to determine whether two files are "the same", to know if we need to copy files. Even if copy-files-mode is turned off, file sameness is important for the analysis phase (described below).

Naïvely using the file-path has several problems:

1. A parallel process might simultaneously replace (delete followed by create) a file while it is being written, resulting in a false-positive for file sameness. The path is the same, but writes happening after the replacement are not visible to readers.
2. Symbolic links, hard links, and `mount`s allow different paths to refer to the same file contents, resulting in a false-negative for file sameness. While symbolic links can be canonicalized, hard links cannot be; none of the hard links is "more canonical" than the others.

Both problems are resolved by identifying file contents by inode number rather than by file path. PROBE asks the filesystem to determine which inode number a filepath actually maps to.

TODO: [OPUS](https://www.usenix.org/conference/tapp13/technical-sessions/presentation/balakrishnan)

# Analysis phase

Now we have a list of provenance operations for each thread in each process in the UNIX process-tree rooted at `<command>` (for `probe record <command>`). We would like to create a dataflow graph on attributes of the system state (especially files).

On these operations, we define three [partial orders](https://www.wikiwand.com/en/Partially_ordered_set):

- Within each thread, the provenance operations are naturally ordered by **program order**.
- However, some provenance operations create an ordering between provenance operations of _different threads or processes_ called **synchronization order**. For example, `fork()` creates ordering between itself and the first provenance operation in the child process (in addition to the _program order_ link to the next provenance operation in the parent process).
- **Happens-before order** is the transitive closure of the union of program order and synchronization order.

Happens-before order appears to be a super-set of dataflow; i.e., there cannot be dataflow from provenance operations A to B if B happens-before A.

This information may __not_ be enough to totally order the relevant ops. TODO

## File dataflow

We ideally want need to _avoid_ logging every individual `read` and `write` for performance reasons. Instead, we look at whether the file was opened for reading, truncating-write, mutating-write-only, or reading-and-mutating-write.

A large class of programs, such as `make`, although they may read and write the same file, do not do so _simultaneously_; rather an interval of writes that happens-before an interval of reads, where both intervals are separated by `open` with the appropriate mode and `close`.

An **interval** in a happens-before graph is a generalization of an interval of time; it is defined by two sets of provenance operations called 'initial' and 'final', and it indicates the set of all nodes in initial, final, or between an element of initial (happens-after) and an element of final (happens-before). For a file, the interval along which it can be accessed begins with an `open` and has one `close` for each `fork` that takes place after the `open` and before the last `close`. This specific interval is called the **open/close interval** of that file.

For all accesses to the same file, we list the open/close intervals. TODO

## Worked exmaple

Consider the provenance logs for `probe record bash -c 'foo < input_file > tmp_file && bar <tmp_file > output_file'`. All of the processes have only one thread.

  - PID 100's provenance log:
    - Exec `bash`
    - Fork (returns 101)
    - Waitpid 101
    - Fork (returns 102)
    - Waitpid 102
  - PID 101's provenance log:
    - Exec `foo`
    - Open `input_file` for reading
    - Open `temp_file` for writing
    - (many reads and writes happen, which we do not track)
    - Close all files
  - PID 102's provenance log:
    - Exec `bar`
    - Open `output_file` for writing
    - Open `temp_file` for reading
    - (many reads and writes happen, which we do not track)
    - Close all files

  The entire close of `temp_file` in PID 101 precedes waitpid 101 in synchronization order, waitpid 101 precedes fork 102 in program order, and fork 102 precedess the open of `temp_file` in PID 102, so we can conclude that information may flow from `foo` to `bar`.

  From which, we can deduce the provenance graph `input_file` -> `foo` -> `temp_file` -> `bar` -> `output_file` with only the open/close intervals and happens-before order.
