import warnings
import httpx
import io
import pathlib
import tarfile
import typing
import yarl
import xml.etree.ElementTree as ET
import githubkit
import githubkit.core
import os
import polars
import cache_util
import charmonium.cache
import charmonium.cache.util
import huggingface_hub


def papers_with_code() -> polars.DataFrame:
    path = huggingface_hub.hf_hub_download(
        repo_id="pwc-archive/links-between-paper-and-code",
        repo_type="dataset",
        filename="data/train-00000-of-00001.parquet",
    )
    return polars.read_parquet(path)


github_client = githubkit.GitHub(githubkit.TokenAuthStrategy(os.environ["GITHUB_PAT"]))
github_client.rest.users.get_authenticated()
github_client = charmonium.cache.util.with_attr(github_client, "__cache_key__", lambda: None)


@charmonium.cache.memoize(group=cache_util.group)
def count_github_stars(owner: str, repo: str) -> int | None:
    try:
        repo_obj = github_client.rest.repos.get(owner, repo)
    except githubkit.core.RequestFailed:
        return None
    else:
        return repo_obj.parsed_data.stargazers_count


namespaces = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


@charmonium.cache.memoize(group=cache_util.group)
def get_linked_papers(arxiv_ids: list[str]) -> typing.Mapping[str, list[str]]:
    assert len(arxiv_ids) < 2000
    url = yarl.URL("https://export.arxiv.org/api/query").with_query(
        id_list=",".join(map(str, arxiv_ids)),
        max_results=len(arxiv_ids) + 1,
    )
    content = httpx.get(str(url), follow_redirects=True).content
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        # Add arxiv_ids as context
        pathlib.Path("test.xml").write_bytes(content)
        raise ValueError(f"Not able to parse {arxiv_ids}; see ./test.xml") from exc
    entries = root.findall("atom:entry", namespaces)
    results = {}
    for entry in entries:
        id_elem = entry.find("atom:id", namespaces)
        assert id_elem is not None
        assert isinstance(id_elem.text, str)
        arxiv_id = yarl.URL(id_elem.text).path_safe.rpartition("/")[-1].rpartition("v")[0]
        results[arxiv_id] = [
            "https://doi.org/" + doi_elem.text
            for doi_elem in entry.findall("arxiv:doi", namespaces)
            if doi_elem.text
        ]
    if difference := set(arxiv_ids) - results.keys():
        warnings.warn(f"Arxiv API failed for {difference}")
    return results


def download_repo_tarball(url_str: str) -> tarfile.TarFile | None:
    url = yarl.URL(url_str)
    archive_url = url.with_path("/".join([*url.path_safe.split("/")[:3], "archive", "HEAD.tar.gz"]))
    tar_bytes = cache_util.download(str(archive_url))
    assert tar_bytes
    if tar_bytes == b'Not Found':
        return None
    else:
        try:
            return tarfile.open(
                fileobj=io.BytesIO(tar_bytes),
                mode="r:gz",
            )
        except tarfile.ReadError as exc:
            print(url_str, tar_bytes[:100], exc)
            raise exc


@charmonium.cache.memoize(group=cache_util.group)
def get_openalex_citations(doi: str) -> int | None:
    assert doi.startswith("https://doi.org/10.")
    response = httpx.get("https://api.openalex.org/works/" + doi + "?mailto=sam@samgrayson.me")
    if response.status_code != 200:
        return None
    else:
        return response.json().get("cited_by_count", 0)


def get_arxiv_doi(arxiv_id: str) -> str | None:
    # See https://info.arxiv.org/help/doi.html
    url = "https://doi.org/10.48550/arXiv." + arxiv_id
    if cache_util.is_url_dereferenceable(url):
        return url
    else:
        return None


def get_arxiv_citations(arxiv_id: str) -> int:
    arxiv_doi = get_arxiv_doi(arxiv_id)
    other_dois = get_linked_papers([arxiv_id]).get(arxiv_id, [])
    return sum(
        get_openalex_citations(doi) or 0
        for doi in [arxiv_doi, *other_dois]
    )
