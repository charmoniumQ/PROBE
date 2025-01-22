# Posix SH compatible source script

red='\033[0;31m'
clr='\033[0m'

project_root="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
printf "project_root = %s\n" "$project_root"

# Rust frontend uses CPATH to find libprobe headers
export CPATH="$project_root/libprobe/include:$CPATH"

# Rust CLI uses __PROBE_LIB to find libprobe binary
export __PROBE_LIB="$project_root/libprobe/build"

# Ensure libprobe.so gets maked
if [ ! -f "$__PROBE_LIB/libprobe.so" ]; then
    printf "%sPlease run 'just compile-lib' to compile libprobe%s\n" "$red" "$clr"
fi

# Rust code uses PYGEN_OUTFILE to determine where to write this file.
export PYGEN_OUTFILE="$project_root/probe_py/probe_py/ops.py"

# Ensure PROBE CLI gets built
if [ ! -f "$project_root/cli-wrapper/target/release/probe" ]; then
    printf "%sPlease run 'just compile-cli' to compile probe binary%s\n" "$red" "$clr"
fi

# Add PROBE CLI to path
export PATH="$project_root/cli-wrapper/target/release:$PATH"

# Add probe_py to the Python path
export PYTHONPATH="$project_root/probe_py/:$PYTHONPATH"
export MYPYPATH="$project_root/probe_py/mypy_stubs:$project_root/probe_py/:$MYPYPATH"
