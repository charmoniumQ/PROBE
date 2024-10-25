import subprocess
import os
import pytest
import tempfile
import paramiko
import time
import shutil

@pytest.fixture(scope="session")
def ssh_server():
    # Directory to store the SSH keys
    ssh_dir = os.path.abspath('./ssh_keys')
    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir)
    
    private_key_path = os.path.join(ssh_dir, "id_rsa")
    public_key_path = private_key_path + ".pub"

    # Generate an RSA SSH keypair
    subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "4096", "-N", "", "-f", private_key_path], check=True)

    # Ensure proper permissions on the private key file
    os.chmod(private_key_path, 0o600)

    # Start the Docker container using docker-compose
    compose_file = "docker-compose.yml"
    subprocess.run(["docker", "compose", "-f", compose_file, "up", "-d"], check=True)

    # Wait for the container to be ready
    time.sleep(10)

    # Remove any previous SSH known_hosts entry for localhost:2222
    subprocess.run(
        ["ssh-keygen", "-f", os.path.expanduser("~/.ssh/known_hosts"), "-R", "[localhost]:2222"],
        check=False
    )

    # Retry connecting with paramiko up to 10 times
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    for _ in range(10):
        try:
            ssh.connect(
                hostname="localhost",
                port=2222,
                username="sshwrapper",
                key_filename=private_key_path,
                allow_agent=False,
                look_for_keys=False
            )
            # Test SSH connection by running a simple command
            ssh.close()
            break
        except (paramiko.ssh_exception.NoValidConnectionsError, paramiko.ssh_exception.AuthenticationException):
            time.sleep(1)
    else:
        raise RuntimeError("SSH server is not ready or failed to authenticate.")

    # Provide the key paths and container info for the test
    yield {
        "ssh_dir": ssh_dir,
        "private_key_path": private_key_path,
        "container_name": "openssh-wrapper",
    }

    # Tear down the container after the test session ends
    subprocess.run(["docker", "compose", "-f", compose_file, "down"], check=True)

    # Cleanup the SSH key directory after tests
    shutil.rmtree(ssh_dir)

