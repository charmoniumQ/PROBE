# Posix SH compatible source script

esc=$(printf '\033')
red="${esc}[0;31m"
clr="${esc}[0m"

export PROBE_ROOT="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
printf "PROBE_ROOT = %s\n" "$PROBE_ROOT"

# Rust CLI uses PROBE_LIB to find libprobe binary
export PROBE_LIB="$PROBE_ROOT/libprobe/.build"

# Ensure libprobe.so gets made
if [ ! -f "$PROBE_LIB/libprobe.so" ]; then
    printf "%sPlease run 'just compile-lib' to compile libprobe%s\n" "$red" "$clr"
fi

# Rust code uses PYGEN_OUTFILE to determine where to write this file.
export PYGEN_OUTFILE="$PROBE_ROOT/probe_py/probe_py/ops.py"

# Rust code uses CBINDGEN_OUTFILE to determine where to write this file.
export CBINDGEN_OUTFILE="$PROBE_ROOT/libprobe/generated/headers.h"
export JSONSCHEMA_OUTFILE="$PROBE_ROOT/libprobe/generated/headers.json"
export PYTHON_HEADER_OUTFILE="$PROBE_ROOT/probe_py/probe_py/headers.py"
export SIZE_CHECK_OUTFILE="$PROBE_ROOT/libprobe/generated/size_checks.h"

# Add PROBE CLI to path
CARGO_TARGET_PATH="$(env --chdir=cli-wrapper cargo metadata --format-version 1 | jq --raw-output '.target_directory')"
export PATH="${CARGO_TARGET_PATH}/debug:$PATH"

# Add probe_py to the Python path
# PYTHONPATH gets consumed by Python tooling
# PROBE_PYTHONPATH gets consumed by `probe py` (works in situations where the environment needs a different `PYTHONPATH`)
export PYTHONPATH="$PROBE_ROOT/probe_py/:$PYTHONPATH"
export PROBE_PYTHONPATH="$PYTHONPATH"
