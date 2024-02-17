#!/usr/bin/env bash

echo result/bin/python runner.py --workloads simple --collectors working --rerun

podman run \
    --privileged \
    --security-opt unmask=/proc/* \
    --security-opt unmask=/sys/fs/cgroup \
    --security-opt seccomp=unconfined \
    --rm \
    --interactive \
    --tty \
    --volume $PWD:$PWD \
    --workdir $PWD \
    prov-tracer-benchmark-env:c9pdwj93y3xwfmfnsxkrw1lcc7wfhn8g
