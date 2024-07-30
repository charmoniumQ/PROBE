# Posix SH compatible source script

red='\033[0;31m'
clr='\033[0m'

# Ensure `nix develop` was called from the root directory.
if [ ! -f flake.nix ]; then
    echo -e "${red}Please cd to the project root before trying to enter the devShell ('nix develop').${clr}"
fi

# Rust frontend uses CPATH to find libprobe headers
export CPATH="$PWD/probe_src/libprobe/include:$CPATH"

# Rust CLI uses __PROBE_LIB to find libprobe binary
export __PROBE_LIB="$PWD/probe_src/libprobe/build"

# Ensure libprobe.so gets maked
if [ ! -f $__PROBE_LIB/libprobe.so ]; then
    echo -e "${red}Please run 'make -C probe_src/libprobe all' to compile libprobe${clr}"
fi

# Rust code uses PYGEN_OUTFILE to determine where to write this file.
# TODO: Replace this with a static path, because it is never not this path.
export PYGEN_OUTFILE="$PWD/probe_src/probe_frontend/python/probe_py/generated/ops.py"

# Ensure PROBE CLI gets built
if [ ! -f probe_src/probe_frontend/target/release/probe ]; then
    echo -e "${red}Please run 'env -C probe_src/probe_frontend cargo build --release' to compile probe binary${clr}"
fi

# Add PROBE CLI to path
export PATH="$PWD/probe_src/probe_frontend/target/release:$PATH"

# Add probe_py.generated to the Python path
export PYTHONPATH="$PWD/probe_src/probe_frontend/python:$PYTHONPATH"
export MYPYPATH="$PWD/probe_src/probe_frontend/python:$MYPYPATH"

# Add probe_py.manual to the Python path
export PYTHONPATH="$PWD/probe_src/python:$PYTHONPATH"
export MYPYPATH="$PWD/probe_src/python:$MYPYPATH"
