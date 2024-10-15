import io
import typing
import tempfile
import sys
import collections.abc
import subprocess
import shlex
import pathlib
import asyncio


project_root = pathlib.Path(__file__).resolve().parent.parent.parent


_T = typing.TypeVar("_T")


def as_completed_with_concurrency(
        n: int,
        coros: typing.Iterable[collections.abc.Awaitable[_T]],
) -> typing.Iterator[asyncio.Future[_T]]:
    semaphore = asyncio.Semaphore(n)
    async def sem_coro(coro: collections.abc.Awaitable[_T]) -> _T:
        async with semaphore:
            return await coro
    return asyncio.as_completed([sem_coro(c) for c in coros])


async def run_in_docker(
        name: str,
        image: str,
        tag: str,
        script: list[list[list[str]]],
        test: list[list[str]],
        capture_output: bool,
        clean: bool,
) -> tuple[str, bool, bytes, bytes]:
    dockerfile = "\n".join([
        f"FROM {image}:{tag}",
        *[
            "RUN " + " && ".join(
                shlex.join(line).replace("double-pipe", "||")
                for line in group
            )
            for group in script
        ],
    ])
    temp_dir = pathlib.Path(tempfile.mkdtemp())
    (temp_dir / "Dockerfile").write_text(dockerfile)
    proc = await asyncio.create_subprocess_exec(
        *["podman", "build", "--tag", name, str(temp_dir)],
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )
    if capture_output:
        stdout, stderr = await proc.communicate()
    else:
        stdout, stderr = b"", b""

    await proc.wait()

    if proc.returncode != 0:
        return name, False, stdout, stderr

    test_str = " && ".join(
        shlex.join(line)
        for line in test
    )
    args = ["podman", "run", "--rm", "--volume", f"{project_root}:{project_root}:ro", name, "bash", "-c", test_str]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=None,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )
    if capture_output:
        result = await proc.communicate()
    else:
        result = b"", b""

    stdout += result[0]
    stderr += result[1]

    await proc.wait()

    return name, not proc.returncode, stdout, stderr


images = [
    ("ubuntu", ["24.04"], [[
        ["apt-get", "update"],
        ["DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "curl"],
        ["rm", "--recursive", "--force", "/var/lib/apt/lists/*"]
    ]]),
    # ("debian", ["8.0", "unstable-slim"], [[
    #     ["apt-get", "update"],
    #     ["DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "curl"],
    #     ["rm", "--recursive", "--force", "/var/lib/apt/lists/*"]
    # ]]),
    # ("fedora-slim", ["23", "41"], []),
    # Alpine uses musl c, which should be interesting
    # ("alpine", ["2.6", "3.20"], []),
]


script = [
    # shlex.quote("|") -> "'|'", which is wrong, so instead we will write the word pipe.
    [
        ["curl", "--proto", "=https", "--tlsv1.2", "-sSf", "-o", "nix-installer", "-L", "https://install.determinate.systems/nix"],
        ["sh", "nix-installer", "install", "linux", "--no-confirm", "--init", "none"],
    ],
    [
        [".", "/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh"],
        ["export", "USER=root"],
        ["nix", "profile", "install", "--accept-flake-config", "nixpkgs#cachix"],
        ["cachix", "use", "charmonium"],
    ],
    [
        ["export", "USER=root"],
        [".", "/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh"],
        ["nix", "build", "-L", "github:charmoniumQ/PROBE#probe-bundled", "double-pipe", "true"],
    ],
]

test = [
    ["export", "USER=root"],
    [".", "/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh"],
    ["nix", "profile", "install", "-L", f"{project_root}#probe-bundled"],
    ["probe", "record", "-f", "stat", "."]
]


async def main(max_concurrency: int, capture_output: bool) -> bool:
    results = as_completed_with_concurrency(max_concurrency, [
        run_in_docker(
            f"probe-{image}-{tag}",
            image,
            tag,
            pre_script + script,
            test,
            capture_output,
            clean=False,
        )
        for image, tags, pre_script in images
        for tag in tags
    ])
    any_failed = False
    for result in results:
        image, success, stdout, stderr = await result
        if not success:
            print(image, "failed")
            sys.stdout.buffer.write(stdout)
            sys.stderr.buffer.write(stderr)
            print("\n")
            any_failed = True
    return any_failed

if asyncio.run(main(
        max_concurrency=1,
        capture_output=False,
)):
    sys.exit(1)
