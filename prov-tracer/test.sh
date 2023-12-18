set -e

cmds=(
    true
    "ls -l .."
    # "echo hi"
    # "head ../flake.nix"
    # "python -c 'print(2)'"
    # "python -c 'import itertools'"
)

cargo build
if [ ! -d tmp ]; then
    mkdir tmp
fi

for cmd in "${cmds[@]}"; do
    echo ============ $cmd ============
    env --chdir=tmp RUST_BACKTRACE=1 LD_PRELOAD=$PWD/target/debug/libprov_tracer.so sh -c "$cmd" &
    pid=$!
    wait
    for file in tmp/*; do
        chmod 644 $file
        cat $file
        rm $file
    done
done
