#!/usr/bin/env bash
set -e
nix build --print-build-logs '.#acm-rep'
cat result/benchmark_suite/main.pdf > benchmark_suite/README.pdf
