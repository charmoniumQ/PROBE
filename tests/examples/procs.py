import multiprocessing
import threading
import pathlib


def f1():
    pathlib.Path("flake.nix").read_text()


def f2():
    pathlib.Path("flake.lock").read_text()


if __name__ == "__main__":
    thread = threading.Thread(target=f1, args=("hello from thread",))
    thread.start()
    proc = multiprocessing.Process(target=f2, args=("hello from proc",))
    proc.start()
    proc.join()
    thread.join()
    print("done")
