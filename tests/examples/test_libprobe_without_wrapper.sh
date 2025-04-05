#!/usr/bin/env bash

set -ex

proj_root="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"

libprobe="$proj_root/libprobe/.build/libprobe.dbg.so"

if [ ! -f "$libprobe" ]; then
    echo "Need to build libprobe first; try 'just compile'"
    exit 1
fi

readelf --all "$libprobe"  | grep 'Type:'

readelf --all "$libprobe" | grep 'NEEDED'

nm --dynamic --defined-only "$libprobe"

nm --dynamic --undefined-only "$libprobe"

export __PROBE_DIR=/tmp/probe/test
if [ -e "$__PROBE_DIR" ]; then
    rm --recursive --force "$__PROBE_DIR"
fi
mkdir --parents "$__PROBE_DIR"

exe="$proj_root/tests/examples/simple.exe"
args="$proj_root/README.md"

# We intentionally want to splat $args here
# shellcheck disable=SC2086
LD_DEBUG=all LD_PRELOAD=$libprobe "$exe" $args

rm --recursive --force "$__PROBE_DIR"
mkdir --parents "$__PROBE_DIR"
libprobe="$(dirname "$libprobe")/libprobe.so"

# We intentionally want to splat $args here
# shellcheck disable=SC2086
LD_PRELOAD=$libprobe "$exe" $args

# if ! LD_DEBUG=all LD_PRELOAD=$libprobe "$exe" $args; then
#     gdb \
#         --quiet \
#         --eval-command="set environment LD_PRELOAD $libprobe" \
#         --eval-command="set environment LD_DEBUG all" \
#         --eval-command="run" \
#         --eval-command="backtrace" \
#         --eval-command="quit" \
#         --args "$exe" $args
#     exit 1
# fi
