import hashlib
import pathlib
import typing
import dataclasses
import functools
import subprocess
import util


@dataclasses.dataclass(frozen=True)
class Placeholder:
    value: str
    postfix: str = ""
    prefix: str = ""

    def expand(self, context: typing.Mapping[str, str]) -> str:
        return self.prefix + context[self.value] + self.postfix


@functools.lru_cache
def nix_build(attr: str) -> str:
    print(f"Nix building {attr}")
    return subprocess.run(
        ["nix", "build", attr, "--print-out-paths", "--no-link"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

@dataclasses.dataclass(frozen=True)
class NixPath:
    package: str
    postfix: str = ""
    prefix: str = ""

    def expand(self) -> str:
        return self.prefix + nix_build(self.package) + self.postfix

    def __hash__(self) -> int:
        return int.from_bytes(hashlib.md5(self.expand().encode()).digest())

    def __eq__(self, other: typing.Any) -> bool:
        if isinstance(other, NixPath):
            return self.expand() == other.expand()
        else:
            return False


@dataclasses.dataclass(frozen=True)
class Command:
    args: tuple[str | NixPath | Placeholder | pathlib.Path, ...]

    def expand(self, context: typing.Mapping[str, str]) -> tuple[str, ...]:
        return tuple(
            arg if isinstance(arg, str) else
            arg.expand() if isinstance(arg, NixPath) else
            str(arg) if isinstance(arg, pathlib.Path) else
            arg.expand(context) if isinstance(arg, Placeholder) else
            util.raise_(TypeError(f"{type(arg)!s}: {arg!r}"))
            for arg in self.args
        )

    def __bool__(self) -> bool:
        return bool(self.args)
