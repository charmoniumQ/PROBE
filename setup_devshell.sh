# Posix SH compatible source script

esc=$(printf '\033')
red="${esc}[0;31m"
clr="${esc}[0m"

export PROBE_ROOT="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
printf "PROBE_ROOT = %s\n" "$PROBE_ROOT"

# Rust frontend uses CPATH to find libprobe headers
export CPATH="$PROBE_ROOT/libprobe/include:$CPATH"

# Rust CLI uses PROBE_LIB to find libprobe binary
export PROBE_LIB="$PROBE_ROOT/libprobe/.build"

# Ensure libprobe.so gets maked
if [ ! -f "$PROBE_LIB/libprobe.so" ]; then
    printf "%sPlease run 'just compile-lib' to compile libprobe%s\n" "$red" "$clr"
fi

# Rust code uses PYGEN_OUTFILE to determine where to write this file.
export PYGEN_OUTFILE="$PROBE_ROOT/probe_py/probe_py/ops.py"

# Rust code uses CBINDGEN_OUTFILE to determine where to write this file.
export CBINDGEN_OUTFILE="$PROBE_ROOT/libprobe/generated/bindings.h"

# Ensure PROBE CLI gets built
if [ ! -f "$PROBE_ROOT/cli-wrapper/target/release/probe" ]; then
    printf "%sPlease run 'just compile-cli' to compile probe binary%s\n" "$red" "$clr"
fi

# Add PROBE CLI to path
export PATH="$PROBE_ROOT/cli-wrapper/target/debug:$PATH"

# Add probe_py to the Python path
# PYTHONPATH gets consumed by Python tooling
# PROBE_PYTHONPATH gets consumed by `probe py` (works in situations where the environment needs a different `PYTHONPATH`)
# MYPYPATH gets consumed by Mypy, which may be slightly different than the PYTHONPATH
export PYTHONPATH="$PROBE_ROOT/probe_py/:$PYTHONPATH"
export PROBE_PYTHONPATH="$PYTHONPATH"
