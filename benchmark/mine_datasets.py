#!/usr/bin/env python
import json
import textwrap
import requests
import functools
import random
import tqdm
import os
import typing
import pathlib
import yarl
import githubkit
import tarfile
import io
import tempfile
import urllib.request
import measure_resources
import mandala.model
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


@functools.cache
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


@op
def get_spack_urls(n: int, n_sample: int | None) -> list[str]:
    storage = mandala.model.Context.current_context.storage
    out = []
    tar = download("https://github.com/spack/spack/archive/v0.22.3.tar.gz")
    script = pathlib.Path("mine_spack_datasets.py").read_text()
    packages_src = storage.unwrap(run_in_spack(tar, script))
    packages = json.loads(packages_src)
    out.append(f"{len(packages)} packages")
    github = get_github_client()
    urls = [
        url
        for package, url_attrs in packages.items()
        for urls in url_attrs.values()
        for url in urls
    ]
    out.append(f"{len(urls)} URLs")
    github_urls, unknowns = parse_github_urls(urls)
    out.append(f"{len(github_urls)} github URLs")
    if n_sample:
        out.append(f"sampling {n_sample}")
        github_urls = random.Random(0).sample(github_urls, n_sample)
    stars = [
        (
            storage.unwrap(get_stars(Ignore(github), owner, repo)) or 0,
            owner,
            repo,
        )
        for owner, repo in tqdm.tqdm(github_urls, desc="Spack GitHub repos")
    ]
    for stars, owner, repo in sorted(stars, reverse=True)[:n]:
        out.append(f"{stars: 6d} https://github.com/{owner}/{repo}")
    return out


@op
def get_ascl_urls(n_urls: int) -> list[str]:
    out = []
    github = get_github_client()
    storage = mandala.model.Context.current_context.storage
    ascl = json.loads(storage.unwrap(download("https://ascl.net/code/json")).decode())
    out.append(f"{len(ascl)} ASCL records")
    # urls = []
    # for record in ascl.values():
    #     for site in record["site_list"]:
    #         urls.append(typing.cast(str, site))
    # out.append(f"{len(urls)} URLs")
    # github_urls = set()
    # for url in urls:
    #     match parse_url(url):
    #         case (owner, repo):
    #             if (owner, repo) not in github_urls:
    #                 github_urls.add((owner, repo))
    #         case None:
    #             pass
    #         case str():
    #             pass
    #         case _:
    #             raise TypeError
    # out.append(f"{len(github_urls)} GitHub URLs")
    # stars = [
    #     (
    #         storage.unwrap(get_stars(Ignore(github), owner, repo)) or 0,
    #         owner,
    #         repo,
    #     )
    #     for owner, repo in tqdm.tqdm(github_urls, desc="ASCL GitHub URLs")
    # ]
    # for stars, owner, repo in sorted(stars, reverse=True)[:n_urls]:
    #     out.append(f"{stars: 6d} https://github.com/{owner}/{repo}")

    citations = []
    for record in tqdm.tqdm(ascl.values(), desc="ASCL ADS AB lookups"):
        n = 0
        for bibcode in (record["described_in"] or []):
            if "adsabs.harvard.edu" in bibcode:
                bibcode = (
                    bibcode
                    # many weird variants of this URL
                    .replace("https://", "")
                    .replace("http://", "")
                    .replace("ui.adsabs.harvard.edu", "")
                    .replace("adsabs.harvard.edu", "")
                    .replace("/#abs/", "")
                    .replace("/abs/", "")
                    .replace("/", "")
                )
                n += storage.unwrap(get_ads_api_citation_count(bibcode))
        citations.append((n, record["ascl_id"]))
    for n, ascl_id in sorted(citations, reverse=True)[:n_urls]:
        out.append(f"{n: 6d} https://www.ascl.net/{ascl_id}")
    return out


@op
def get_joss_urls(n: int) -> list[str]:
    # https://openalex.org/works?page=1&filter=primary_location.source.publisher_lineage%3Ap4310315853&view=report,api
    results = requests.get(
        f"https://api.openalex.org/works?page=1&filter=primary_location.source.publisher_lineage:p4310315853&sort=cited_by_count:desc&per_page={n}"
    ).json()["results"]
    out = []
    for result in results:
        count = result["cited_by_count"]
        doi = result["doi"]
        out.append(f"{count: 5d} {doi}")
    return out



def get_oci_citation_count(doi: str) -> int | None:
    return json.loads(
        download(f"https://opencitations.net/index/api/v2/citation-count/doi:{doi}").decode()
    )[0]["count"]


@op
def get_ads_api_citation_count(ads_bibcode: str) -> int | None:
    url = yarl.URL.build(
        scheme="https",
        host="api.adsabs.harvard.edu",
        path="/v1/search/query",
        query={
            "q": "bibcode:" + ads_bibcode,
            "fl": "citation_count",
        },
    )
    resp = requests.get(
        str(url),
        headers={
            "Authorization": "Bearer " + os.environ["ADS_API_KEY"],
        },
    )
    try:
        docs = json.loads(resp.text)["response"]["docs"]
    except Exception as exc:
        print(resp.status_code, repr(ads_bibcode), repr(url), resp.text)
        raise exc
    if docs:
        return docs[0]["citation_count"]
    else:
        return 0


storage_path = pathlib.Path(".cache/mine_datasets.db")
storage_path.parent.mkdir(exist_ok=True)
storage = Storage(
    db_path=storage_path,
)
with storage:
    print("Started main")
    print(textwrap.indent("\n".join(storage.unwrap(get_spack_urls(10, None))), "Spack: "))
    print(textwrap.indent("\n".join(storage.unwrap(get_ascl_urls(10))), "ASCL: "))
    print(textwrap.indent("\n".join(storage.unwrap(get_joss_urls(10))), "JOSS: "))
