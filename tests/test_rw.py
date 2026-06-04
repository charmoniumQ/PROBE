import pathlib
import multiprocessing


def source() -> None:
    pathlib.Path("a").write_text("hello")


def sink() -> None:
    pathlib.Path("a").read_text()


for function in [source, sink]:
    process = multiprocessing.Process(target=function)
    process.start()
    process.join()
    process.close()
