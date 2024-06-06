import tarfile
import pathlib
import typer
from . import parse_probe_log


app = typer.Typer()


@app.command()
def dump(probe_log_tar_file: pathlib.Path):
    probe_log_tar = tarfile.open(probe_log_tar_file)
    all_ops = parse_probe_log.parse_probe_log_tar(probe_log_tar)
    for thread_ops in all_ops:
        for op in thread_ops:
            print(op.data)
        print()
    probe_log_tar.close()

app()
