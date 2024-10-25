import os
import subprocess
import paramiko
import pathlib
import tarfile
import json

def test_ssh_wrapper_command_execution(ssh_server):
    env = os.environ.copy()
    env["__PROBE_LIB"] = "../../libprobe/build"  # Ensure the libprobe path is correctly set

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Connect via SSH wrapper and run a command
    wrapper_cmd = [
        "python", "-m", "probe_py.manual.cli", "ssh", "--", "-i", ssh_server["private_key_path"], "-p", "2222",
        "sshwrapper@localhost", "ls"
    ]

    result = subprocess.run(wrapper_cmd, env=env, capture_output=True)
    assert result.returncode == 0, f"SSH Wrapper command failed: {result.stderr.decode()}"

    # Now connect using paramiko to verify the raw SSH execution
    ssh.connect(
        hostname="localhost",
        port=2222,
        username="sshwrapper",
        key_filename=ssh_server["private_key_path"],
        allow_agent=False,
        look_for_keys=False
    )
    
    stdin, stdout, stderr = ssh.exec_command("ls")
    raw_ssh_output = stdout.read().decode().strip()
    ssh.close()

    assert raw_ssh_output, "Raw SSH command failed to execute"

    # Check the provenance log to ensure it's parseable
    local_temp_dir = pathlib.Path("./ssh_keys")  # Assuming provenance logs are downloaded here
    provenance_tar_path = list(local_temp_dir.glob("*.tar.gz"))[0]  # Find the tar file

    # Extract and read the provenance log
    with tarfile.open(provenance_tar_path) as tar:
        tar.extractall(path=local_temp_dir)
    
    provenance_log_path = local_temp_dir / "probe_log.json"  # Example provenance log file

    assert provenance_log_path.exists(), "Provenance log not found"

    # Check if the log is parseable
    with open(provenance_log_path, 'r') as f:
        provenance_data = json.load(f)

    assert isinstance(provenance_data, dict), "Provenance log is not a valid JSON object"
    print(f"Provenance log successfully parsed: {provenance_data}")

