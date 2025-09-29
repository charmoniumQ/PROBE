from __future__ import annotations
import asyncio
import urllib.parse
import pathlib
import tempfile
import typing
import pydantic
import yaml
import util


class Repo(pydantic.BaseModel):
    location: Location
    environment: Environment
    commands: list[str]

    def dockerfile(self) -> list[str]:
        return [
            f"FROM {self.environment.base_image}",
            *self.environment.get_rootful_steps(),
            "COPY --from=localhost/probe:0.1.0 /nix /probe /",
            "RUN useradd --system --user-group user --create-home",
            "USER user",
            "COPY --chown=user:user . /home/user/repo",
            "WORKDIR /home/user/repo",
            *self.environment.get_rootless_steps(),
            "COPY --chown=user:user run.sh .",
        ]

    async def to_docker(
            self,
            tag: str,
            verbose: bool,
    ) -> None:
        repo_dir = cache_dir / urllib.parse.quote_plus(str(self.location.url))
        if not repo_dir.exists():
            await util.async_subprocess_run(
                [
                    "git", "clone", "--quiet", str(self.location.url), str(repo_dir),
                ],
                hide_output=not verbose,
            )
            await util.async_subprocess_run(
                [
                    "git", "-C", str(repo_dir), "checkout", self.location.commit,
                ],
                hide_output=not verbose,
            )
        run = repo_dir / "run.sh"
        run.write_text("#!/usr/bin/env bash\nset -euxo pipefail\n" + "\n".join(self.commands))
        run.chmod(0o755)
        dockerfile_path = repo_dir / "Dockerfile"
        dockerfile_source = self.dockerfile()
        print("Building:")
        for line in dockerfile_source:
            print("  " + line)
        dockerfile_path.write_text("\n".join(dockerfile_source))
        await util.async_subprocess_run(
            ["podman", "build", f"--file={dockerfile_path}", f"--tag={tag}", str(repo_dir)],
            hide_output=not verbose,
        )


class Environment(pydantic.BaseModel):
    base_image: str = "ubuntu:24.04"
    apt_packages: list[str] = []
    python: str | None = None
    pip_packages: list[str] = []

    def get_rootful_steps(self) -> list[str]:
        apt_packages = self.apt_packages
        if self.python is not None:
            apt_packages.extend([f"python{self.python}", "python3-venv"])
        if apt_packages:
            return [
                "RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y " + " ".join(apt_packages),
            ]
        else:
            return []

    def get_rootless_steps(self) -> list[str]:
        if self.pip_packages:
            return [
                f"RUN python{self.python} -m venv ./venv",
                "ENV PATH=\"/home/user/repo/venv/bin:$PATH\"",
                "RUN pip install " + " ".join(self.pip_packages),
            ]
        else:
            return []


class Location(pydantic.BaseModel):
    url: pydantic.AnyUrl
    commit: typing.Annotated[
        str,
        pydantic.constr(min_length=40, max_length=40, pattern="[a-f0-9]+"),
    ]


repos: list[Repo] = pydantic.TypeAdapter(list[Repo]).validate_python(
    yaml.safe_load(
        pathlib.Path("repos.yaml").read_text()
    )
)


cache_dir = pathlib.Path(".cache").resolve()
if not cache_dir.exists():
    cache_dir.mkdir()


def main(
        name: str,
) -> None:
    for repo in repos:
        if (repo.location.url.path or "").endswith("/" + name):
            break
    else:
        print(f"Repo {name} not found")
        raise typer.Abort()
    asyncio.run(repo.to_docker(name, True))


if __name__ == "__main__":
    import typer
    typer.run(main)
