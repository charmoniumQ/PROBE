#!/usr/bin/env sh

make

LD_PRELOAD="$PWD/minimal_libprobe.so" ./fcat.exe /dev/null

LD_PRELOAD="$PWD/minimal_libprobe.so" ./fork_exec.exe ./fcat.exe /dev/null

LD_PRELOAD="$PWD/minimal_libprobe.so" ./hello_world_pthreads.exe
