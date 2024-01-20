import subprocess
import sys
import signal
import json


server_prog = json.loads(sys.argv[1])
client_prog = json.loads(sys.argv[2])


main_proc = subprocess.Popen(
    server_prog,
)

load_proc = subprocess.run(
    client_prog,
    check=True,
    capture_output=True,
)

main_proc.send_signal(signal.SIGTERM)
