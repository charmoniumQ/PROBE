# Commands and Options

### probe record

| Option | Alternative | Description |
|--------|-------------|-------------|
| -o, | --output | <PATH>  Set destinaton for recording. |
| -f, | --overwrite | Overwrite existing output if it exists. |
| -n, | --no-transcribe | Emit PROBE record rather than PROBE log. |
| --gdb |  | Run under gdb. |
| --debug |  | Run in verbose & debug build of libprobe. |
| -h, | --help | Print help |
| -V, | --version | Print version |

### probe transcribe

| Option | Alternative | Description |
|--------|-------------|-------------|
| -f, | --overwrite | Overwrite existing output if it exists. |
| -o, | --output | <PATH>  Path to write the transcribed PROBE log. [default: probe_log] |
| -i, | --input | <PATH>   Path to read the PROBE record from. [default: probe_record] |
| -h, | --help | Print help |
| -V, | --version | Print version |

### probe dump

| Option | Alternative | Description |
|--------|-------------|-------------|
| --json |  | Output JSON. |
| -i, | --input | <PATH>  Path to load PROBE log from. [default: probe_log] |
| -h, | --help | Print help |
| -V, | --version | Print version |

### probe validate

| Option | Parameter | Description |
|--------|-------------|-------------|
| probe_log | [PROBE_LOG] | output file written by `probe record -o $file`. [default: probe_log] |
| should_have_files | [SHOULD_HAVE_FILES] | Whether to check that the probe_log was run with --copy-files. [default: False] |

### probe ssh

| Option | Parameter | Description |
|--------|-------------|-------------|
| ssh_args | SSH_ARGS... | [default: None] [required] |

### probe export ops-graph

| Option | Parameter | Description |
|--------|-------------|-------------|
| output | [OUTPUT] | [default: ops-graph.png] |
| probe_log | [PROBE_LOG] | output file written by `probe record -o $file`. [default: probe_log] |

### probe export dataflow-graph

| Option | Parameter | Description |
|--------|-------------|-------------|
| output | [OUTPUT] | [default: dataflow-graph.png] |
| probe_log | [PROBE_LOG] | output file written by `probe record -o $file`. [default: probe_log] |

### probe export debug-text

| Option | Parameter | Description |
|--------|-------------|-------------|
| probe_log | [PROBE_LOG] | output file written by `probe record -o $file`. [default: probe_log] |

### probe export docker-image

| Option | Parameter | Description |
|--------|-------------|-------------|
| image_name | TEXT | [default: None] [required] |
| probe_log | [PROBE_LOG] | output file written by `probe record -o $file`. [default: probe_log] |

### probe export oci-image

| Option | Parameter | Description |
|--------|-------------|-------------|
| image_name | TEXT | [default: None] [required] |
| probe_log | [PROBE_LOG] | output file written by `probe record -o $file`. [default: probe_log] |

### probe export makefile

| Option | Parameter | Description |
|--------|-------------|-------------|
| output | [OUTPUT] | [default: Makefile] |
| probe_log | [PROBE_LOG] | output file written by `probe record -o $file`. [default: probe_log] |

