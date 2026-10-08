import pathlib
import threading


project_root = pathlib.Path(__file__).resolve().parent.parent.parent


def f1() -> None:
    (project_root / "flake.nix").read_text()


def f2() -> None:
    (project_root / "flake.lock").read_text()


if __name__ == "__main__":
    (project_root / "README.md").read_text()
    thread1 = threading.Thread(target=f1, args=())
    thread2 = threading.Thread(target=f2, args=())
    thread1.start()
    thread2.start()
    thread1.join()
    thread2.join()
    (project_root / "setup_devshell.sh").read_text()
