#!/usr/bin/env python

import os
import time
import subprocess
import sys
import signal
import pathlib
sys.stderr.write(sys.executable)
import psutil

shell = "bash"

server_prog = sys.argv[1]
client_prog = sys.argv[2]
if len(sys.argv) == 3:
    check_prog = None
elif len(sys.argv) == 4:
    check_prog = sys.argv[3]
else:
    raise RuntimeError("Unexpected number of arguments")

print("$", server_prog, "&")
server_proc = subprocess.Popen(
    [shell, "-c", server_prog],
)

sleeped = False
if check_prog is not None:
    for check in range(50):
        print("Check", check, "$", check_prog)
        proc = subprocess.run([shell, "-c", check_prog], check=False)
        if proc.returncode == 0:
            break
        time.sleep(0.1)
        sleeped = True
    else:
        raise RuntimeError("Check program never came back positive")

if not psutil.Process(server_proc.pid).is_running():
    print("Server program unexpectedly quit")
    sys.exit(1)

print("$", client_prog)
load_proc = subprocess.run(
    [shell, "-c", client_prog],
    check=False,
)

# subprocess.run(["pstree", "--show-pids", "--show-parents", str(server_proc.pid)])

print(f"Terminating server prog {server_proc.pid}")
# Note that in some ptrace programs (reprozip, possibly strace) this will leave a zombie process
# which causes this process to wait forever at the end.
# As a test, write an inf_loop.sh and run the following
#   strace -o /dev/null -f result/bin/sh -c '(./inf_loop.sh; echo hi) & pid=$! ; sleep 0.1 ; echo killing $pid ; kill -9 $pid ; echo entering wait ; wait ; echo exiting wait'
# or
#   strace -o /dev/null -f result/bin/python run_server_and_client.py './inf_loop.sh; echo hi' 'sleep 0.1'
# On my system, it kills the process, enters and exits the wait, but does not actually terminate (it gets stuck after the last echo but before returning 0).
# My debugging indicates this happens because there is a child process that never gets killed and waited on.
# Therefore, I will kill the chilren processes first.

# os.kill(server_proc.pid, signal.SIGKILL)


# https://psutil.readthedocs.io/en/latest/#kill-process-tree
def kill_proc_tree(pid, sig=signal.SIGTERM, include_parent=True,
                   timeout=None, on_terminate=None):
    """Kill a process tree (including grandchildren) with signal
    "sig" and return a (gone, still_alive) tuple.
    "on_terminate", if specified, is a callback function which is
    called as soon as a child terminates.
    """
    assert pid != os.getpid(), "won't kill myself"
    parent = psutil.Process(pid)
    children = parent.children(recursive=True)
    if include_parent:
        children.append(parent)
    for p in children:
        try:
            print(f"Sending {p.pid} {sig}")
            p.send_signal(sig)
            print("Sent")
        except psutil.NoSuchProcess:
            pass
    gone, alive = psutil.wait_procs(children, timeout=timeout,
                                    callback=on_terminate)
    return (gone, alive)

try:
    exited_codes, alive_pids = kill_proc_tree(server_proc.pid, timeout=1)
except Exception as exc:
    print(str(exc))

for pid in alive_pids:
    print(f"{pid} is still alive; sending {signal.SIGKILL}")
    os.kill(pid, signal.SIGKILL)

print(f"Exiting {load_proc.returncode}")
sys.exit(load_proc.returncode)
