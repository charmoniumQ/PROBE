import typing
import subprocess
import urllib.parse
import pathlib
import dulwich.porcelain
import shirty.client


client = shirty.client.ShirtyClient()
response = client.models.info(mode="chat")


def analyze_files(root: pathlib.Path) -> list[tuple[pathlib.Path, str]]:
    ret = []
    for path in root.glob("**"):
        ret.append((path, file_type(path)))
    return ret


def analyze_repo(url: str) -> typing.list[str]:
    path = download_repo(url)
    return {
        (path, file_type(path))
        for path in path.iterdir()
    }
