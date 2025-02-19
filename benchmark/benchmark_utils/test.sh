#!/usr/bin/env bash

set -ex

# Ensure provenance tracers are accurate

tmp=$(mktemp --directory)

./target/debug/audit --log-file "$tmp/test" head Cargo.toml > "$tmp/audit_out"
grep Cargo.toml "$tmp/test"
rm "$tmp/test"

./target/debug/audit --log-file "$tmp/test" head Cargo.toml > "$tmp/ebpf_out"
grep Cargo.toml "$tmp/test"
rm "$tmp/test"

# Ensure timers create output

./target/debug/cgroupv2_time --output "$tmp/test" head Cargo.toml > "$tmp/cgroupv2_out"
jq . "$tmp/test"
rm "$tmp/test"

./target/debug/wait4_time --output "$tmp/test" head Cargo.toml > "$tmp/wait4_out"
jq . "$tmp/test"
rm "$tmp/test"

# Ensure wrappers run
./target/debug/systemd_shield --cpus 3 head Cargo.toml > "$tmp/shield_out"

./target/debug/stabilize --cpus 3 head Cargo.toml > "$tmp/stabilize_out"

./target/debug/limit head Cargo.toml > "$tmp/limit_out"

# Ensure all outputs are the same
sha256sum "$tmp"/*_out

# Ensure failure code propagation
! ./target/debug/audit --log-file "$tmp/test"       false || exit 1
! ./target/debug/audit --log-file "$tmp/test"       false || exit 1
! ./target/debug/cgroupv2_time --output "$tmp/test" false || exit 1
! ./target/debug/wait4_time --output "$tmp/test"    false || exit 1
! ./target/debug/systemd_shield --cpus 3            false || exit 1
! ./target/debug/stabilize --cpus 3                 false || exit 1
! ./target/debug/limit                              false || exit 1

# Ensure no priv escalation
[ "$(./target/debug/audit --log-file "$tmp/test"       whoami)" = "$(whoami)" ]
[ "$(./target/debug/audit --log-file "$tmp/test"       whoami)" = "$(whoami)" ]
[ "$(./target/debug/cgroupv2_time --output "$tmp/test" whoami)" = "$(whoami)" ]
[ "$(./target/debug/wait4_time --output "$tmp/test"    whoami)" = "$(whoami)" ]
[ "$(./target/debug/systemd_shield --cpus 3            whoami)" = "$(whoami)" ]
[ "$(./target/debug/stabilize --cpus 3                 whoami)" = "$(whoami)" ]
[ "$(./target/debug/limit                              whoami)" = "$(whoami)" ]
