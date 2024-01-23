import time
import subprocess
import sys
import signal
import pathlib

shell = str(pathlib.Path("result/bin").resolve() / "sh")

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
    for check in range(20):
        print("Check", check, "$", check_prog)
        proc = subprocess.run([shell, "-c", check_prog], check=True)
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
print("Killing server prog")
main_proc.send_signal(signal.SIGTERM)
sys.exit(load_proc.returncode)
