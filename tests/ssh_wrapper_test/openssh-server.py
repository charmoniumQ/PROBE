import subprocess
import threading
import os


def run_openssh_server() -> None:
    os.chdir("./openssh-server/")
    process = subprocess.Popen(
        "docker compose up -d",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print("""
    OpenSSH server is up:
    port = 2222
    destination = sshwrapper@localhost
    Press "q" and Enter to stop the server.
    """)

    def wait_for_input() -> None:
        while True:
            user_input = input()
            if user_input.strip().lower() == "q":
                print("Stopping OpenSSH server...")
                process.terminate()
                process.wait()
                print("OpenSSH server stopped.")
                break

    input_thread = threading.Thread(target=wait_for_input)
    input_thread.start()

    input_thread.join()


if __name__ == "__main__":
    run_openssh_server()
