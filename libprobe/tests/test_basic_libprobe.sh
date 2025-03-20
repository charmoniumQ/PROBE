#!/usr/bin/env bash

dir="$(realpath "$(dirname "$(dirname "$0")")")"
libprobe="$dir/build/libprobe.dbg.so"

if [ ! -f "$libprobe" ]; then
    echo "Need to build libprobe first; try 'just compile'"
    exit 1
fi

readelf --all "$libprobe"  | grep 'Type:'

readelf --all "$libprobe" | grep 'NEEDED'

nm --dynamic ../build/libprobe.dbg.so

export __PROBE_DIR=/tmp/probe/test
if [ -e "$__PROBE_DIR" ]; then
    rm --recursive --force "$__PROBE_DIR"
fi
mkdir --parents "$__PROBE_DIR"

exe=/home/sam/box/PROBE/tests/examples/simple.exe
args=Makefile

gdb --eval-command="set environment LD_PRELOAD $libprobe" --eval-command="run" --args "$exe" $args
