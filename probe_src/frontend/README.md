
# PROBE Frontend

Tools for recording and manipulating libprobe provenance.

## Serialization formats

### Probe record directory

The format of the probe record directory is defined by libprobe and not part of
this tool's spec, however a best-effort explanation is still given.

- Each probe record directory is composed of a top-level directory containing
one or more PID directories.

- Each PID directory has a numeric name corresponding to the PID of the process
who's provenance is recorded inside it, and in turn contains one or more exec
epoch directories.

- Each exec epoch directory has a numeric name corresponding to the exec epoch
of the virtual memory space who's provenance is recorded inside it, and in turn
contains one or more TID directories.

- Each TID directory has a numeric name corresponding to the TID of the thread
who's provenance is recorded inside it, it contains two subdirectories named
`data` and `ops`

- The `data` and `ops` directories both contains one or more files of the form
`X.dat` where `X` is a number, the `.dat` files inside the `data` directory are
called "data arenas", while those in the `ops` directory are called "op arenas".

- Each op arena is a binary file containing an arena header followed by zero or
more op c structs, followed by zero or more null bytes.

- Each data arena is a binary file containing an arena header followed by zero
or more bytes of arbitrary data, followed by zero or more null bytes.

**note:** these files contain
[mmap(2)](https://www.man7.org/linux/man-pages/man2/mmap.2.html)-ed c structures
and are not guaranteed to valid if moved to a computer with a different
architecture, kernel version, or c compiler (or if any of those things change on
the same computer), and may not be properly decoded by versions of the cli with
even patch version differences.

### Probe log directory

This format **is** part of this tool's spec, and this tool is the source of
truth for its format.

- The format of the top-level, PID, and exec epoch directories is the same as
for the probe record directory described above, but rather than containing TID
directories, each exec epoch directory contains one or more TID files.

- Each TID file has a numeric name corresponding to the TID of the thread who's
provenance is recorded inside it. It is a [jsonlines](https://jsonlines.org/)
file, where each line is an op (as defined in this library) serialized as json.

### Probe log file

This format is simply a probe log directory that's bundled into a tar archive
and compressed with gzip, since its easier to move as a single file and
compresses well.
