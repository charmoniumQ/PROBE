#!/usr/bin/env bash

if [ "$(whoami)" != "root" ]; then
    echo "Run as root (sorry)"
    echo "prov_bpf.c is more agreeable to the security conscious user."
    echo "Just use this for debugging."
    exit 1
fi

log_file=$1
shift
export BPFTRACE_STRLEN=200
dir=$(dirname $0)

./wait_for_signal.py SIGUSR1 100.0 "$@" &
cmd_pid=$!

echo -n > "${log_file}"
$dir/result/bin/bpftrace -B full -f json -o "${log_file}" prov.bt "$cmd_pid" &
bpf_pid=$!

sleep 1

"${dir}/result/bin/kill" -SIGUSR1 "${cmd_pid}"

wait $cmd_pid
cmd_status=$?

wait $bpf_pid
bpf_pid=$?

exit "$((cmd_status | bpf_pid))"
