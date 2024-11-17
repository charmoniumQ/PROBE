# Posix SH compatible source script

red='\033[0;31m'
clr='\033[0m'

project_root="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
echo -e "project_root = ${project_root}"

# Rust frontend uses CPATH to find libprobe headers
export CPATH="$project_root/libprobe/include:$CPATH"

# Rust CLI uses __PROBE_LIB to find libprobe binary
export __PROBE_LIB="$project_root/libprobe/build"

# Ensure libprobe.so gets maked
if [ ! -f "$__PROBE_LIB/libprobe.so" ]; then
    echo -e "${red}Please run 'just compile-lib' to compile libprobe${clr}"
fi

# Rust code uses PYGEN_OUTFILE to determine where to write this file.
# TODO: Replace this with a static path, because it is never not this path.
export PYGEN_OUTFILE="$project_root/probe_py/probe_py/ops.py"

# Ensure PROBE CLI gets built
if [ ! -f $project_root/probe_src/frontend/target/release/probe ]; then
    echo -e "${red}Please run 'just compile-cli' to compile probe binary${clr}"
fi

# Add PROBE CLI to path
export PATH="$project_root/cli-wrapper/target/release:$PATH"

# Add probe_py to the Python path
export PYTHONPATH="$project_root/probe_py/:$PYTHONPATH"
export MYPYPATH="$project_root/probe_py/mypy_stubs:$project_root/:$MYPYPATH"
