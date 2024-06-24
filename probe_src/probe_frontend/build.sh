#!/bin/sh

set -e
cd "$(dirname "$(realpath "$0")")"
mkdir -p ./include
cp ../libprobe/include/prov_ops.h ./include/prov_ops.h
git add ./include
nix build
git restore --staged ./include
