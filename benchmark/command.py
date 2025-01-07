import datetime
import hashlib
import pathlib
import typing
import dataclasses
import subprocess
import util
import json
from mandala.imports import Storage, op
import mandala.model


storage = Storage(".cache/nix_build.db")


@dataclasses.dataclass(frozen=True)
class Placeholder:
    value: str
    postfix: str = ""
    prefix: str = ""

    def expand(self, context: typing.Mapping[str, str]) -> str:
        return self.prefix + context[self.value] + self.postfix


def nix_build(attr: str) -> str:
    # Cache nix build, since it is expensive
    # Even if nothing cahnges, Nix takes ~0.3 seconds to determine that nothing changed.
    if attr.startswith(".#"):
        # If the flake is changed, the mandala cache is invalid
        # Therefore, make the Nix flake and lock an argument tracked by Mandala.
        return mandala.model.Context.current_context.storage.unwrap(_nix_build(
            attr,
            pathlib.Path("flake.nix").read_text(),
            json.loads(pathlib.Path("flake.lock").read_text()),
        ))
    else:
        return _nix_build(attr, "", None)


@op
def _nix_build(attr: str, flake_src: str, flake_lock: typing.Any) -> str:
    print(f"Nix building {attr}")
    start = datetime.datetime.now()
    ret = subprocess.run(
        ["nix", "build", attr, "--print-out-paths", "--no-link"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(f"Nix built {attr} in {(datetime.datetime.now() - start).total_seconds()}")
    return ret

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

    def __getstate__(self) -> typing.Mapping[str, str]:
        # Mandala uses joblib.hash which uses pickle to get the state of an object for hashing purposes.
        # We want to override this to depend on the state of the Nix flake as well.
        return {"expanded": self.expand()}


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
