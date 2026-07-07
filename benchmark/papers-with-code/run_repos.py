from __future__ import annotations
import asyncio
import subprocess
import os
import pathlib
import typing
import shlex
import shutil
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
            if int(self.python.split(".")[1]) >= 10:
                # Starting with x = 10, python3.x is the name of an Ubuntu package.
                apt_packages.append(f"python{self.python}")
                apt_packages.append(f"python{self.python}-venv")
            else:
                # Prior to 3.10, you get whatever Python version that version of Ubuntu has :)
                ubuntu_python = {
                    "ubuntu:20.04": "3.8",
                    "ubuntu:18.04": "3.6",
                }[self.base_image]
                if ubuntu_python != self.python:
                    raise ValueError(f"No easy way to install Python {self.python} on {ubuntu_python} (rewrite to use pyenv?)")
                apt_packages.append("python3")
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

    async def to_docker(
            self,
            name: str,
            probe_tag: str,
            podman_or_docker: str,
            tag: str,
            de_escalate: bool,
            dry_run: bool,
            verbose: bool,
    ) -> None:
        work_dir = cache_dir / name
        if not work_dir.exists():
            work_dir.mkdir()

        if self.location is not None:
            repo_dir = work_dir / "repo"
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
            copy_repo_command = ["COPY --chown=user:user repo /home/user/repo"]
        else:
            copy_repo_command = []

        if self.unrecorded_commands:
            pre_run = work_dir / "pre_run.sh"
            pre_run.write_text("#!/usr/bin/env bash\nset -euxo pipefail\n" + "\n".join(self.unrecorded_commands))
            pre_run.chmod(0o755)
            copy_pre_run_command = ["COPY --chown=user:user pre_run.sh ."]
        else:
            copy_pre_run_command = []

        if self.commands:
            run = work_dir / "run.sh"
            run.write_text("#!/usr/bin/env bash\nset -euxo pipefail\n" + "\n".join(self.commands))
            run.chmod(0o755)
            copy_run_command = ["COPY --chown=user:user run.sh ."]
        else:
            copy_run_command = []


        if "SSL_CERT_FILE" in os.environ:
            # Copy from root, but make me the owner of the copy.
            with pathlib.Path(os.environ["SSL_CERT_FILE"]).open("rb") as input:
                with (work_dir / "cert.pem").open("wb") as output:
                    shutil.copyfileobj(input, output)
            cert_commands = [
                "COPY cert.pem /cert.pem",
                "ENV SSL_CERT_FILE=/cert.pem \\",
                "    PIP_CERT=/cert.pem \\",
                "    REQUESTS_CA_BUNDLE=/cert.pem",
            ]
        else:
            cert_commands = []
        # http_proxy has to be lowercase.
        # See https://everything.curl.dev/usingcurl/proxies/env.html
        proxy_var_values = [
            f"{var}={os.environ[var]}"
            for var in ["https_proxy", "http_proxy", "HTTPS_PROXY", "HTTP_PROXY", "no_proxy"]
            if var in os.environ
        ]
        if proxy_var_values:
            proxy_var_commands = ["ENV " + " ".join(proxy_var_values)]
        else:
            proxy_var_commands = []

        if de_escalate:
            de_escalate_cmds = ["USER user"]
        else:
            de_escalate_cmds = []

        dockerfile_source = [
            f"FROM {self.environment.base_image}",
            *proxy_var_commands,
            *cert_commands,
            *self.environment.get_rootful_steps(),
            "RUN useradd --system --user-group user --create-home",
            *de_escalate_cmds,
            *copy_repo_command,
            "WORKDIR /home/user/repo",
            *self.environment.get_rootless_steps(),
            f"COPY --from=probe:{probe_tag} /nix /nix",
            f"COPY --from=probe:{probe_tag} /bin/probe /bin/probe",
            *copy_pre_run_command,
            *copy_run_command,
        ]

        dockerfile_path = work_dir / "Dockerfile"
        dockerfile_path.write_text("\n".join(dockerfile_source))

        if verbose:
            print("Building:")
            for line in dockerfile_source:
                print("  " + line)

        cmd = [podman_or_docker, "build", f"--file={dockerfile_path}", f"--tag={tag}", str(work_dir)]
        if dry_run:
            print(shlex.join(cmd))
        else:
            await util.async_subprocess_run(cmd, hide_output=not verbose)


subproject_root = pathlib.Path(__file__).resolve().parent
project_root = subproject_root.parent.parent.parent


repos: list[Repo] = pydantic.TypeAdapter(list[Repo]).validate_python(
    yaml.safe_load(
        (subproject_root / "repos.yaml").read_text()
    )
)


cache_dir = pathlib.Path(".cache2").resolve()
if not cache_dir.exists():
    cache_dir.mkdir()


def main(
        name: str,
        probe_tag: str = "0.0.13",
        podman_or_docker: str = "docker",
        verbose: bool = True,
        dry_run: bool = True,
        de_escalate: bool = False,
        downloads_dir = pathlib.Path(".cache2")
) -> None:
    for repo in repos:
        if repo.name == name:
            break
    else:
        print(f"Repo {name} not found")
        raise typer.Abort()
    asyncio.run(repo.to_docker(name, probe_tag, podman_or_docker, f"{name}:{probe_tag}", de_escalate, dry_run, verbose))
    cmd = [
        podman_or_docker,
        "run",
        f"--volume={downloads_dir}:/downloads",
        "--volume=/nix:/nix",
        "--interactive",
        "--tty",
        "--rm",
        f"{name}:{probe_tag}",
    ]
    if dry_run:
        print(shlex.join(cmd))
    else:
        subprocess.run(cmd)


if __name__ == "__main__":
    import typer
    typer.run(main)
