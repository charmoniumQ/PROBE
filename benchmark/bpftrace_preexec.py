import select
import sys
import subprocess
import time
import pathlib

pid_fifo = pathlib.Path(sys.argv[1])
ready_fifo = pathlib.Path(sys.argv[2])
log_file = pathlib.Path(sys.argv[3])

assert pid_fifo.is_fifo() # so we can use select on it
assert ready_fifo.is_fifo()

buffer = ""
with open(pid_fifo, "r") as pid_fifo_obj:
    while not buffer or buffer[-1] != "\n":
        select.select([pid_fifo_obj], [], [])
        buffer += pid_fifo_obj.read()
pid = int(buffer.strip())
print("Got pid", pid)
proc = subprocess.Popen(
    ["./unprivileged_bpftrace.exe", log_file, "-e", str(pid)],
)
print("Waiting for bpftrace to be ready")
ready = False
while not ready:
    if log_file.exists():
        with open(log_file, "r") as log_file_obj:
            for line in log_file_obj:
                if "launch_pid" in line:
                    ready = True
                    break
    if not ready:
        time.sleep(0.001)
print("Sending ready")
with open(ready_fifo, "w") as ready_fifo_obj:
    ready_fifo_obj.write("ready\n")
proc.wait()
sys.exit(proc.returncode)
