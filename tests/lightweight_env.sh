#!/usr/bin/env bash

# nix develop brings in a ton of stuff to the env
# which complicates testing probe
# To simplify, use this script.

project_root="$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]}")")")"

path="$project_root/cli-wrapper/target/release"

env - PROBE_LIB="$PROBE_LIB" PATH="$path" "${@}"
