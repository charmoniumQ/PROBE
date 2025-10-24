#!/usr/bin/env bash

LD_LIBRARY_PATH="$(nix eval --raw nixpkgs#gcc-unwrapped.lib)/lib:$(nix eval --raw nixpkgs#zlib.out)/lib:${LD_LIBRARY_PATH}"
export LD_LIBRARY_PATH
