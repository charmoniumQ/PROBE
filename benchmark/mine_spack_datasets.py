import spack.repo  # type: ignore
import collections
import json
import typing


verbose: bool = False
urls: typing.Mapping[str, typing.Mapping[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))


pkg_names = spack.repo.PATH.all_package_names(include_virtuals=True)
for i, pkg_name in enumerate(pkg_names):
    if i % 100 == 0 and verbose:
        print(f"on package {i} of {len(pkg_names)}")
    pkg_class = spack.repo.PATH.get_pkg_class(pkg_name)
    if git := getattr(pkg_class, "git", None):
        if isinstance(git, str):
            urls[pkg_name]["git"].append(git)
        elif isinstance(git, property):
            urls[pkg_name]["git"].append(git.__get__(pkg_class))
        elif verbose:
            print(pkg_name, "git", git, str(git))
    if url := getattr(pkg_class, "url", None):
        if not isinstance(url, str) and verbose:
            print(pkg_name, "url", url, str(url))
        urls[pkg_name]["url"].append(url)
    if homepage := getattr(pkg_class, "homepage", None):
        if not isinstance(homepage, str) and verbose:
            print(pkg_name, "homepage", homepage, str(homepage))
        urls[pkg_name]["homepage"].append(homepage)
    for version in getattr(pkg_class, "versions", {}).values():
        if url := version.get("url", None):
            if not isinstance(url, str) and verbose:
                print(pkg_name, "version", url, str(url))
            urls[pkg_name]["version_url"].append(url)


print(json.dumps({pkg_name: dict(attrs) for pkg_name, attrs in urls.items()}))
