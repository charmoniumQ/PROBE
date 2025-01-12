#!/usr/bin/env python
import subprocess
import urllib.request
import urllib.error
import sys


def terminate_or_kill(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(1)
    except subprocess.TimeoutExpired:
        proc.kill()


n_requests = int(sys.argv[1])
url = sys.argv[2]
server_cmd = sys.argv[3:]
server_proc = subprocess.Popen(server_cmd)


for check in range(20):
    try:
        urllib.request.urlopen(url, timeout=1)
    except urllib.error.URLError:
        print("Server not up yet")
    else:
        break
else:
    terminate_or_kill(server_proc)
    print("Server never came up")
    sys.exit(1)


subprocess.run(["hey", "-n", str(n_requests), url])
terminate_or_kill(server_proc)
