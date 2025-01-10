#!/usr/bin/env python
import json
import random
import tqdm
import os
import asyncio
import typing
import pathlib
import yarl
import githubkit
import tarfile
import io
import tempfile
import util
import urllib.request
import measure_resources
from mandala.imports import Storage, Ignore, op


@op
def download(url: str) -> bytes:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as req:
        ret = req.read()
    print("Done")
    return ret


@op
def run_in_spack(spack_tar: bytes, script: str) -> typing.Any:
    strip1 = lambda member, path: member.replace(name=pathlib.Path(*pathlib.Path(member.path).parts[1:]))
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = pathlib.Path(_tmpdir)
        with tarfile.open(
                name=None,
                mode="r",
                fileobj=io.BytesIO(spack_tar),
                bufsize=10240,
        ) as spack_tar_obj:
            spack_tar_obj.extractall(tmpdir, filter=strip1)
        script_py = (tmpdir / "script.py")
        script_py.write_text(script)
        proc = measure_resources.measure_resources(
            (
                "bash", "-c", f"source {tmpdir}/share/spack/setup-env.sh && spack python {script_py}",
            ),
        )
        proc.raise_for_error()
        return proc.stdout.decode()


def get_github_client() -> githubkit.GitHub:
    github_pat = os.environ["GITHUB_PAT"]
    github = githubkit.GitHub(githubkit.TokenAuthStrategy(github_pat))
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
def get_stars(github: githubkit.GitHub, owner: str, repo: str) -> int | None:
    try:
        repo_obj = github.rest.repos.get(owner, repo)
    except githubkit.exception.RequestFailed:
        return None
    else:
        stars = repo_obj.parsed_data.stargazers_count
        return stars


def parse_github_urls(urls: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    dispatched = set()
    unknown = []
    for url in tqdm.tqdm(urls, desc="URLs"):
        result = parse_url(url)
        match result:
            case (owner, repo):
                if (owner, repo) not in dispatched:
                    dispatched.add((owner, repo))
            case None:
                pass
            case str():
                unknown.append(result)
            case _:
                raise TypeError
    return sorted(dispatched), unknown
    return [
        (get_stars(Ignore(github), owner, repo), owner, repo)
        for owner, repo in tqdm.tqdm(dispatched, "GitHub URLs")
    ], unknown


storage_path = pathlib.Path(".cache/mine_datasets.db")
storage_path.parent.mkdir(exist_ok=True)
storage = Storage(
    db_path=storage_path,
)
with storage:
    print("Started main")
    spack_tar = download("https://github.com/spack/spack/archive/v0.22.3.tar.gz")
    script = pathlib.Path("mine_spack_datasets.py").read_text()
    spack_packages_src = storage.unwrap(run_in_spack(spack_tar, script))
    print(spack_packages_src[:100])
    spack_packages = json.loads(spack_packages_src)
    github = get_github_client()
    urls = [
        url
        for package, url_attrs in spack_packages.items()
        for urls in url_attrs.values()
        for url in urls
    ]
    print(f"{len(urls)} packages")
    github_urls, unknowns = parse_github_urls(urls)
    print(f"{len(github_urls)} github URLs")
    print(f"{len(unknowns)} unknown URLs")
    for unknown in unknowns:
        print("unknown URL", unknown)
    github_urls = random.Random(0).sample(github_urls, 800)
    stars = [
        (storage.unwrap(get_stars(Ignore(github), owner, repo)) or 0, owner, repo)
        for owner, repo in tqdm.tqdm(github_urls, desc="Repos")
    ]
    stars = sorted(stars, reverse=True)

    for stars, owner, repo in stars[:30]:
        print(stars, owner, repo)
