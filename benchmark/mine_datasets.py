import tqdm
import asyncio
import typing
import json
import pathlib
import yarl
import githubkit
import tarfile
import io
import tempfile
import subprocess
import urllib.request
from mandala.imports import Storage, op


DB_PATH = 'my_persistent_storage.db'
storage = Storage(
    db_path="cache.db",
    deps_path='__main__',
)


@op
def download(url: str) -> bytes:
    block_size = 1024 * 10
    with urllib.request.urlopen(url) as req:
        length = req.info()["Content-Length"]
        buf = b""
        with tqdm.tqdm(desc="bytes downloaded", total=length, unit="bytes", unit_scale=True) as bar:
            chunk = b" "
            while chunk:
                chunk = req.read(block_size)
                buf += chunk
                bar.update(len(chunk))


@op
def run_in_spack(spack_tar: bytes, script: str) -> typing.Any:
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        with tarfile.open(name=None, mode='r', fileobj=io.BytesIO(spack_tar), bufsize=10240) as spack_tar_obj:
            spack_tar_obj.extractall(tmpdir, filter="data")
        script_py = (tmpdir / "script.py").write_text(script)
        return subprocess.run(
            [
                "bash", "-c", f"source {tmpdir}/spack/share/spack/setup-env.sh && spack python {script_py}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout


def get_github_client() -> githubkit.GitHub:
    raise NotImplementedError()
    github = githubkit.GitHub()
    github.rest.users.get_authenticated()
    return github

# Possible GitHub APIs:
#
# https://github.com/AnswerDotAI/ghapi
# https://github.com/ludeeus/aiogithubapi
# https://github.com/yanyongyu/githubkit?tab=readme-ov-file
#
# Criteria:
# - async
# - typed
# - rate limiting


def parse_url(url: str) -> str | None | tuple[str, str]:
    if url is None:
        return None
    elif not isinstance(url, str):
        return f"Got {type(url)}, {repr(url)}, {str(url)}"
    url2 = yarl.URL(url)
    if url2.scheme == "file":
        return None
    elif not url2.host:
        return f"no host in {url}"
    elif ".github.io" in url2.host or ".github.com" in url2.host:
        owner = url2.host.split(".")[0]
        repo = url2.path.split("/")[1]
        return (owner, repo)
    elif url2.host == "github.com" or url2.host == "www.github.com":
        if url2.path.count("/") >= 2:
            _, owner, repo = url2.path.split("/")[:3]
            return (owner, repo)
        else:
            return f"weird github {url}"
    elif "github" in url2.host:
        return f"weird github {url}"
    else:
        return None


@op
async def get_stars(github: githubkit.GitHub, owner: str, repo: str) -> tuple[int, str, str]:
    stars = (await github.rest.repos.async_get(owner, repo)).parsed_data.stargazers_count
    return (stars, owner, repo)


@op
async def urls_to_stars(github: githubkit.GitHub, urls: list[str]) -> tuple[list[tuple[int, str, str]], list[str]]:
    dispatched = set()
    awaitables = []
    unknown = []
    for url in urls:
        result = parse_url(url)
        match result:
            case (owner, repo):
                if (owner, repo) not in dispatched:
                    dispatched.add((owner, repo))
                    awaitables.append(get_stars(github, owner, repo))
            case None:
                pass
            case str():
                unknown.append(result)
            case _:
                raise TypeError
    return (await await_all(awaitables, desc="repos")), unknown


_T = typing.TypeVar("_T")
async def await_all(
        awaitables: list[typing.Awaitable[_T]],
        desc: None | str = None,
) -> list[_T]:
    return sorted([
        await awaitable
        for awaitable in tqdm.tqdm(asyncio.as_completed(awaitables), total=len(awaitables))
    ])


with storage:
    spack_tar = download("https://github.com/spack/spack/archive/v0.22.3.tar.gz")
    script = pathlib.Path("mine_spack_datasets.py").read_text()

cf = storage.cf(download)
    # spack_packages = json.loads(run_in_spack(spack_tar, script))
    # github = get_github_client()
    # urls = [
    #     url
    #     for package, url_attrs in spack_packages.items()
    #     for urls in url_attrs.values()
    #     for url in urls
    # ]
    # print(f"{len(urls)} packages")
    # stars, unknowns = asyncio.run(urls_to_stars(github, urls))
    # for unknown in unknowns:
    #     print("unknown URL", unknown)

    # for stars, owner, repo in stars[:30]:
    #     print(stars, owner, repo)
