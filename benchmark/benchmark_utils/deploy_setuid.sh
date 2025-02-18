#!/usr/bin/env bash

set -e

if [ "$1" = "run" ]; then
    run=true
else
    run=
fi

cargo fmt
# git add -A .
# cargo clippy --fix --allow-staged --allow-dirty
cargo build
cargo build --release
if [ -z "$run" ]; then
    echo "Please execute the following commands, some of which use sudo:"
    echo
    echo "cd $PWD"
fi

if [ -z "$run" ]; then
    echo "sudo chown root target/{release,debug}/{stabilize,systemd_shield,audit,ebpf_trace_prov}"
    echo "sudo chmod 6750 target/{release,debug}/{stabilize,systemd_shield,audit,ebpf_trace_prov}"
else
    set -x
    sudo chown root target/{release,debug}/{stabilize,systemd_shield,audit,ebpf_trace_prov}
    sudo chmod 6750 target/{release,debug}/{stabilize,systemd_shield,audit,ebpf_trace_prov}
fi
