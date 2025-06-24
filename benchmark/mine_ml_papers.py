#!/usr/bin/env python
from __future__ import annotations

import functools
import gzip
import io
import json
import os
import pathlib
import typing
import urllib.request

import tqdm
import yarl
import githubkit
import mandala.model 
from mandala.imports import op, Ignore  
from mandala.imports import Storage    


PWC_LINKS_URL = (
    "https://paperswithcode.com/media/about/links-between-papers-and-code.json.gz"
)
CACHE_DB = pathlib.Path(".cache/mine_ml_papers.db")

@op
def download(url: str) -> bytes:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as req:
        data = req.read()
    print(f"Fetched {len(data)/1_048_576:.1f} MiB")
    return data


@op
def decompress_json_gz(blob: bytes) -> list[dict]:
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as gz:
        return typing.cast(list[dict], json.loads(gz.read().decode()))


def parse_url(url: str | None) -> typing.Union[None, tuple[str, str], str]:
    if not url:
        return None
    u = yarl.URL(url)
    if u.host in {"github.com", "www.github.com"}:
        parts = u.path.strip("/").split("/")
        return (parts[0], parts[1]) if len(parts) >= 2 else f"bad github url {url}"
    if u.host and u.host.endswith(".github.io"):
        owner = u.host.split(".")[0]
        repo = u.path.strip("/").split("/")[0]
        return owner, repo
    return None


@functools.cache
def get_github_client() -> githubkit.GitHub:
    gh = githubkit.GitHub(githubkit.TokenAuthStrategy(os.environ["GITHUB_PAT"]))
    gh.rest.users.get_authenticated()
    return gh


@op
def get_stars(gh: githubkit.GitHub, owner: str, repo: str) -> int | None:
    try:
        resp = gh.rest.repos.get(owner, repo)
    except githubkit.exception.RequestFailed:
        return None
    return resp.parsed_data.stargazers_count


@op
def collect_pipelines(official_only: bool = False) -> list[tuple[str, str, int | None]]:
    storage = mandala.model.Context.current_context.storage
    raw = storage.unwrap(download(PWC_LINKS_URL))
    records = storage.unwrap(decompress_json_gz(raw))

    gh_links: dict[tuple[str, str], dict] = {}
    for rec in records:
        if official_only and not rec.get("is_official", False):
            continue
        parsed = parse_url(rec.get("repo_url"))
        if isinstance(parsed, tuple):
            gh_links.setdefault(parsed, rec)

    print(f"{len(gh_links):,} unique GitHub repos")
    gh = get_github_client()

    out: list[tuple[str, str, int | None]] = []
    for (owner, repo), rec in tqdm.tqdm(gh_links.items(), desc="GitHub stars"):
        stars = storage.unwrap(get_stars(Ignore(gh), owner, repo))
        out.append((f"https://github.com/{owner}/{repo}", rec["paper_title"], stars))
    return out


def main(top_n: int = 20, official_only: bool = False) -> None:
    storage = Storage(db_path=CACHE_DB)
    with storage:
        results = storage.unwrap(collect_pipelines(official_only))
        best = sorted(results, key=lambda r: (r[2] or -1), reverse=True)[:top_n]
        for url, title, stars in best:
            star_str = f"{stars:,}" if stars is not None else " ? "
            print(f"{star_str:>7}  {url}\n        {title}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Mine ML pipelines from PWC")
    ap.add_argument("-n", "--top-n", type=int, default=20)
    ap.add_argument("--official-only", action="store_true")
    main(**vars(ap.parse_args()))
