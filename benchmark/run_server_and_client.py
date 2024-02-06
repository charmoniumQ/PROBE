import time
import subprocess
import sys
import signal
import pathlib
import psutil

result_bin = pathlib.Path("result/bin").resolve()
shell = str(result_bin / "sh")

server_prog = sys.argv[1]
client_prog = sys.argv[2]
if len(sys.argv) == 3:
    check_prog = None
elif len(sys.argv) == 4:
    check_prog = sys.argv[3]
else:
    raise RuntimeError("Unexpected number of arguments")

print("$", server_prog, "&")
main_proc = subprocess.Popen(
    [shell, "-c", server_prog],
)

if check_prog is not None:
    for check in range(50):
        print("Check", check, "$", check_prog)
        proc = subprocess.run([shell, "-c", check_prog], check=False)
        if proc.returncode == 0:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Check program never came back positive")

print("$", client_prog)
load_proc = subprocess.run(
    [shell, "-c", client_prog],
    check=False,
    capture_output=True,
)

sys.stdout.buffer.write(load_proc.stdout)
sys.stderr.buffer.write(load_proc.stderr)

subprocess.run([str(result_bin / "pstree"), "--show-pids", "--show-parents", str(main_proc.pid)])

print(f"Killing server prog {main_proc.pid}")
# Note that in some ptrace programs (reprozip, possibly strace) this will leave a zombie process
# which causes this process to wait forever at the end.
# As a test, write an inf_loop.sh and run the following
#   strace -o /dev/null -f result/bin/sh -c '(./inf_loop.sh; echo hi) & pid=$! ; sleep 0.1 ; echo killing $pid ; kill -9 $pid ; echo entering wait ; wait ; echo exiting wait'
# On my system, it kills the process, enters and exits the wait, but does not actually terminate (it gets stuck after the last echo but before returning 0).
# My debugging indicates this happens because there is a child process that never gets killed and waited on.
# Therefore, I will kill the chilren processes first.
def kill_proc_and_children(proc: psutil.Process, timeout: float) -> None:
    for child in proc.children(recursive=False):
        kill_proc_and_children(child, timeout)
    proc.terminate()
    proc.wait(timeout)
    if proc.is_running():
        proc.kill()

kill_proc_and_children(psutil.Process(main_proc.pid), 1.0)

sys.exit(load_proc.returncode)
