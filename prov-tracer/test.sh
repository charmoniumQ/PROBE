#!/usr/bin/env bash
set -e -x

cmds=(
    # "true"
    # "ls -l .."
    # "head ../flake.nix"
    # "../tests/forking_exec"
    "../tests/raw_exec"
    # "python -c 'print(2)'"
    # "python -c 'import itertools'"
    # "python -c 'import os, pathlib; list(pathlib.Path().iterdir()); os.chdir(\"..\"); list(pathlib.Path().iterdir())'"
)

cargo build
if [ ! -d tmp ]; then
    mkdir tmp
fi

for cmd in "${cmds[@]}"; do
    echo ============ $cmd ============
    env --chdir=tmp RUST_BACKTRACE=1 LD_PRELOAD=$PWD/target/debug/libprov_tracer.so $cmd &
    pid=$!
    wait $pid
    success="$?"
    if [ -n "$(ls tmp)" ]; then
        for file in tmp/*; do
            chmod 644 $file
            cat $file
            rm $file
        done
    fi
    if [ "${success}" -ne 0 ]; then
        break
    fi
done
exit "${success}"
