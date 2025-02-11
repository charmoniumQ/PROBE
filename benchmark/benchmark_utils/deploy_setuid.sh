#!/bin/sh

set -e

if [ "$1" = "run" ]; then
    run=true
else
    run=
fi

cargo fmt
# git add -A .
# cargo clippy --fix --allow-staged --allow-dirty
cargo build --release
if [ -z "$run" ]; then
    echo "Please execute the following commands, some of which use sudo:"
    echo
    echo "cd $PWD"
fi

setuid_bins="stabilize systemd_shield audit ebpf_trace_prov"
for setuid_bin in $setuid_bins; do
    # I solemnly swear that $setuid_bin does not contain a space, dollar, quote, or other weird character.
    # In exchange, I won't need to put apostrophes around '$setuid_bin'.
    if [ -z "$run" ]; then
        echo "sudo rm --force $setuid_bin"
        echo "cp target/release/$setuid_bin $setuid_bin"
        echo "sudo chown root $setuid_bin"
        echo "sudo chmod 6750 $setuid_bin"
    else
        sudo rm --force "$setuid_bin"
        cp "target/release/$setuid_bin" "$setuid_bin"
        sudo chown root "$setuid_bin"
        sudo chmod 6750 "$setuid_bin"
    fi

done
