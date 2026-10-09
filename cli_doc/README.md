# Commands and Options

## probe record

Execute a command and record its provenance

| Option | Description |
|--------|-------------|
| `<CMD>...` | Command to execute under provenance. |
| `-o, --output <PATH>` | Set destination for recording. |
| `-f, --overwrite` | Overwrite existing output if it exists. |
| `-r, --fix-random` | Fix the value of /dev/u?random. |
| `-n, --no-transcribe` | Emit PROBE record rather than PROBE log. |
| `--gdb` | Run under gdb. |
| `--debug` | Run in verbose & debug build of libprobe. |
| `-e, --copy-files <COPY_FILES>` | Whether/how to copy files that would be needed to re-execute the program. [default: none] [possible values: none, lazily, eagerly] |

## probe transcribe

Convert PROBE records to PROBE logs.

| Option | Description |
|--------|-------------|
| `-f, --overwrite` | Overwrite existing output if it exists. |
| `-o, --output <PATH>` | Path to write the transcribed PROBE log. [default: probe_log] |
| `-i, --input <PATH>` | Path to read the PROBE record from. [default: probe_record] |

## probe py validate

Sanity-check probe_log and report errors.

| Option | Description |
|--------|-------------|
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
| `--should-have-files / --no-should-have-files` | Whether to check that the probe_log was run with copied files. [default: no-should-have-files] |
| `--strict / --loose` | Whether to fail when PROBE generates warnings [default: strict] |
| `--debug / --no-debug` | Whether to enter a debugger on errors [default: no-debug] |

## probe py op-counts

Print the number of ops.

| Option | Description |
|--------|-------------|
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |

## probe py ssh

Wrap SSH and record provenance of the remote command.

| Option | Description |
|--------|-------------|
| `SSH_ARGS...` |  |
| `--debug / --no-debug` | Run verbose & debug build of libprobe [default: no-debug] |

## probe py scp

| Option | Description |
|--------|-------------|
| `CMD...` |  |

## probe py export hb-graph

Write a happens-before graph on the operations in probe_log.

| Option | Description |
|--------|-------------|
| `[OUTPUT]` | [default: hb-graph.dot] |
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
| `--retain [all\|minimal\|file\|successful]` | Which ops to include in the graph? There are quite a few. [default: successful] |
| `--show-op-number / --no-show-op-number` | Whether to show the op number in the output. [default: no-show-op-number] |
| `--strict / --loose` | Whether to fail when PROBE generates warnings [default: strict] |
| `--debug / --no-debug` | Whether to enter a debugger on errors [default: no-debug] |

## probe py export dataflow-graph

Write a dataflow graph for probe_log.

| Option | Description |
|--------|-------------|
| `[OUTPUT]` | [default: dataflow-graph.dot] |
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
| `--ignore-paths TEXT` | Comma-separated glob/fnmatch [default: /nix/store/*,/dev/*,/proc/*,/sys/*,*.pyc,*/.local/state/nix/profile/*,*/.venv/*,/tmp/*] |
| `--include-paths TEXT` | Comma-separated glob/fnmatch |
| `--strict / --loose` | Whether to fail when PROBE generates warnings [default: strict] |
| `--debug / --no-debug` | Whether to enter a debugger on errors [default: no-debug] |
| `--verbose / --no-verbose` | Whether to have verbose output [default: no-verbose] |
| `--conservative / --no-conservative` | Err on the side of adding an edge rather than missing one. [default: no-conservative] |

## probe py export workflow

| Option | Description |
|--------|-------------|
| `--output PATH` | [default: workflow.yaml] |
| `--ignore-paths TEXT` | Comma-separated glob/fnmatch [default: /nix/store/*,/dev/*,/proc/*,/sys/*,*.pyc,*/.local/state/nix/profile/*,*/.venv/*,/tmp/*] |
| `--include-paths TEXT` | Comma-separated glob/fnmatch |
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
| `--strict / --loose` | Whether to fail when PROBE generates warnings [default: strict] |
| `--debug / --no-debug` | Whether to enter a debugger on errors [default: no-debug] |
| `--verbose / --no-verbose` | Whether to have verbose output [default: no-verbose] |
| `--conservative / --no-conservative` | Err on the side of adding an edge rather than missing one. [default: no-conservative] |

## probe py export w3c-prov

| Option | Description |
|--------|-------------|
| `--rdf-output PATH` | [default: provenance.ttl] |
| `--graphical-output PATH` | [default: provenance.dot] |
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
| `--ignore-paths TEXT` | Comma-separated glob/fnmatch [default: /nix/store/*,*/__pycache__/*,/dev/*,/proc/*,/sys/*,*.pyc,*/.local/state/nix/profile/*] |
| `--include-paths TEXT` | Comma-separated glob/fnmatch |
| `--strict / --loose` | Whether to fail when PROBE generates warnings [default: strict] |
| `--debug / --no-debug` | Whether to enter a debugger on errors [default: no-debug] |
| `--verbose / --no-verbose` | Whether to have verbose output [default: no-verbose] |
| `--conservative / --no-conservative` | Err on the side of adding an edge rather than missing one. [default: no-conservative] |

## probe py export store-dataflow-graph

| Option | Description |
|--------|-------------|
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |

## probe py export debug-text

Write the data from probe_log in a human-readable manner.

| Option | Description |
|--------|-------------|
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
| `[OUTPUT]` | [default: debug-text.txt] |
| `--strip-env / --no-strip-env` | [default: strip-env] |

## probe py export docker-image

Generate a docker image from a probe_log with --copy-files.

| Option | Description |
|--------|-------------|
| `IMAGE_NAME` |  |
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
| `--verbose / --no-verbose` | [default: verbose] |

## probe py export oci-image

Generate an OCI image from a probe_log with --copy-files.

| Option | Description |
|--------|-------------|
| `IMAGE_NAME` |  |
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
| `--verbose / --no-verbose` | [default: verbose] |

## probe py export process-tree

Write a process tree from probe_log.

| Option | Description |
|--------|-------------|
| `--output PATH` | [default: probe_log-process-tree.dot] |
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |

## probe py export ops-jsonl

Export each op to a JSON line.

| Option | Description |
|--------|-------------|
| `--probe-log, -f PATH` | output file written by `probe record -o $file`. [default: probe_log] |
