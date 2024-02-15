import sys
import os
import pathlib
import select

pid_fifo = pathlib.Path(sys.argv[1])
ready_fifo = pathlib.Path(sys.argv[2])
exe = pathlib.Path(sys.argv[3])
args = sys.argv[3:]

assert pid_fifo.is_fifo()
assert ready_fifo.is_fifo()
assert exe.is_file()

pid = os.getpid()

print(f"Sending {pid=}")

with open(pid_fifo, "w") as pid_fifo_obj:
    pid_fifo_obj.write(str(pid) + "\n")

print("Waiting for ready signal")
with open(ready_fifo, "r") as ready_fifo_obj:
    while True:
        select.select([ready_fifo_obj], [], [])
        if ready_fifo_obj.read(1):
            break

print("Got ready signal")
os.execv(exe, args)
