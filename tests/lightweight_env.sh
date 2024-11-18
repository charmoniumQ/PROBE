#!/usr/bin/env bash

# nix develop brings in a ton of stuff to the env
# which complicates testing probe
# To simplify, use this script.

env - __PROBE_LIB=$__PROBE_LIB PATH=$PATH PYTHONPATH=$PYTHONPATH $@
