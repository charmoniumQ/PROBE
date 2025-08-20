#!/usr/bin/env sh

set -ex

log_file="logs/test"
conf_dir="conf"
dirs="/home/sam/box/PROBE/benchmark/benchmark_utils"
audit="/nix/store/3pswbqvm7nvb1nlj03xs790871l1y9fy-audit-4.0-bin"
arch="$(uname -m)"

#########

# Create log file
log_file="$(realpath --canonicalize-missing "$log_file")"
log_dir="$(dirname "$log_file")"
sudo rm --force --recursive "$log_dir"
sudo mkdir "$log_dir"
sudo touch "$log_file"
sudo chmod 0600 "$log_file"

# Create conf dir
conf_dir="$(realpath --canonicalize-missing "$conf_dir")"
sudo rm --force --recursive "$conf_dir"
sudo mkdir "$conf_dir"

# Create conf
cat <<EOF | sudo tee "$conf_dir/auditd.conf" > /dev/null
log_file = $log_file
log_format = ENRICHED
space_left = 100
space_left_action = suspend
EOF

# Create rules
sudo "$audit/bin/auditctl" -D > /dev/null
sudo $audit/bin/auditctl -a always,exit -F "arch=$arch" -F uid=1000 -F gid=100 -S clone,clone3,fork,vfork,execve,execveat,exit,exit_group -k clone
# clone,clone3,fork,vfork,execve,execveat,exit,exit_group
# sudo $audit/bin/auditctl -a exit,always -F "arch=$arch" -F uid=1000 -F gid=100 -S \
#     clone,clone3,fork,vfork,execve,execveat,exit,exit_group,bind,accept,accept4,connect,shutdown,pipe,pipe2
for dir in $dirs; do
    dir="$(realpath "$dir")"
    sudo $audit/bin/auditctl -a exit,always -F "arch=$arch" -F uid=1000 -F gid=100 -F "dir=$dir" -k dir
done
# sudo $audit/bin/auditctl -a task,never
# sudo $audit/bin/auditctl -a exit,never
# sudo $audit/bin/auditctl -a user,never
# sudo $audit/bin/auditctl -a filesystem,never
sudo $audit/bin/auditctl -e 1 -f 1 --reset-lost
echo 'Rules:'
sudo $audit/bin/auditctl -l

sudo $audit/bin/auditd -n -c "$conf_dir" &
pid=$!

echo 'Main:'
sleep 0.1
head /home/sam/box/PROBE/benchmark/benchmark_utils/Cargo.toml
ls /home/sam/box/PROBE/benchmark/benchmark_utils/src
sudo kill -s TERM "$pid"

sudo $audit/bin/auditctl -D > /dev/null

sudo chown "$(id -u):$(id -g)" "$log_file" "$log_dir"
# cat "$log_file"
