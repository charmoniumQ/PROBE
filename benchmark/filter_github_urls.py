import asyncio
import typing
import json
import pathlib
import yarl
import rich.progress
import githubkit

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


progress = rich.progress.Progress()


github = githubkit.GitHub("...")
resp = github.rest.users.get_authenticated()


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


async def get_stars(owner: str, repo: str) -> tuple[int, str, str]:
    stars = (await github.rest.repos.async_get(owner, repo)).parsed_data.stargazers_count
    return (stars, owner, repo)


async def main() -> None:
    with progress:
        spack_package_urls = json.loads(pathlib.Path("spack_package_urls.json").read_text())
        githubs: list[typing.Awaitable[tuple[int, str, str]]] = []
        for package, url_attrs in spack_package_urls.items():
            for urls in url_attrs.values():
                for url in urls:
                    result = parse_url(url)
                    match result:
                        case (owner, repo):
                            githubs.append(get_stars(owner, repo))
                        case None:
                            pass
                        case str():
                            print(result)
                        case _:
                            raise TypeError
        for result2 in progress.track(asyncio.as_completed(githubs), total=len(githubs)):
            print(await result2)


if __name__ == "__main__":
    asyncio.run(main())
