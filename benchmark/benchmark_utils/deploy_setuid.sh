#!/bin/sh

cargo build
setuid_bins="stabilize systemd_shield systemd_time"
for setuid_bin in $setuid_bins; do
    echo "$setuid_bin"
    sudo rm --force "$setuid_bin"
    cp target/debug/"$setuid_bin" "$setuid_bin"
    sudo chown root "$setuid_bin"
    sudo chmod u+s "$setuid_bin"
done
