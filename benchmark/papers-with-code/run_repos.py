from __future__ import annotations
import asyncio
import urllib.parse
import pathlib
import shutil
import typing
import pydantic
import yaml
import util


class Environment(pydantic.BaseModel):
    base_image: str = "ubuntu:24.04"
    apt_packages: list[str] = []
    python: str | None = None
    venv_commands: list[str] = []

    def get_rootful_steps(self) -> list[str]:
        apt_packages = self.apt_packages
        if self.python is not None:
            apt_packages.append(f"python{self.python}")
        if self.venv_commands is not None:
            apt_packages.append("python3-venv")
        if apt_packages:
            return [
                "RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y " + " ".join(apt_packages),
            ]
        else:
            return []

    def get_rootless_steps(self) -> list[str]:
        if self.venv_commands:
            return [
                f"RUN python{self.python} -m venv ./venv",
                "ENV PATH=\"/home/user/repo/venv/bin:$PATH\"",
                "RUN " + " && ".join(self.venv_commands),
            ]
        else:
            return []


class Location(pydantic.BaseModel):
    url: pydantic.AnyUrl
    commit: typing.Annotated[
        str,
        pydantic.constr(min_length=40, max_length=40, pattern="[a-f0-9]+"),
    ]


class Repo(pydantic.BaseModel):
    name: str
    environment: Environment = Environment()
    location: Location | None = None
    unrecorded_commands: list[str] = []
    commands: list[str] = []

    def dockerfile(self, probe_tag: str) -> list[str]:
        return [
            f"FROM {self.environment.base_image}",
            *self.environment.get_rootful_steps(),
            f"COPY --from=probe:{probe_tag} /nix /nix",
            f"COPY --from=probe:{probe_tag} /bin/probe /bin/probe",
            "RUN useradd --system --user-group user --create-home",
            "USER user",
            *(["COPY --chown=user:user . /home/user/repo"] if self.location is not None else []),
            "WORKDIR /home/user/repo",
            *self.environment.get_rootless_steps(),
            *(["COPY --chown=user:user pre_run.sh ."] if self.unrecorded_commands else []),
            *(["COPY --chown=user:user run.sh ."] if self.commands else []),
        ]

    async def to_docker(
            self,
            probe_tag: str,
            podman_or_docker: str,
            tag: str,
            verbose: bool,
    ) -> None:
        if self.location is not None:
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
        else:
            repo_dir = cache_dir / "tmp"
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            repo_dir.mkdir()
        if self.unrecorded_commands:
            pre_run = repo_dir / "pre_run.sh"
            pre_run.write_text("#!/usr/bin/env bash\nset -euxo pipefail\n" + "\n".join(self.unrecorded_commands))
            pre_run.chmod(0o755)
        if self.commands:
            run = repo_dir / "run.sh"
            run.write_text("#!/usr/bin/env bash\nset -euxo pipefail\n" + "\n".join(self.commands))
            run.chmod(0o755)
        dockerfile_path = repo_dir / "Dockerfile"
        dockerfile_source = self.dockerfile(probe_tag)
        if verbose:
            print("Building:")
            for line in dockerfile_source:
                print("  " + line)
        dockerfile_path.write_text("\n".join(dockerfile_source))
        await util.async_subprocess_run(
            [podman_or_docker, "build", f"--file={dockerfile_path}", f"--tag={tag}", str(repo_dir)],
            hide_output=not verbose,
        )


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
        probe_tag: str = "0.0.4",
        podman_or_docker: str = "docker",
        verbose: bool = True,
) -> None:
    for repo in repos:
        if repo.name == name:
            break
    else:
        print(f"Repo {name} not found")
        raise typer.Abort()
    asyncio.run(repo.to_docker(probe_tag, podman_or_docker, f"{name}:{probe_tag}", verbose))


if __name__ == "__main__":
    import typer
    typer.run(main)
