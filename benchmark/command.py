import measure_resources
import hashlib
import pathlib
import typing
import dataclasses
import util
import json
from mandala.imports import op  # type: ignore
import mandala.model  # type: ignore


def nix_build(attr: str) -> str:
    # Cache nix build, since it is expensive
    # Even if nothing cahnges, Nix takes ~0.3 seconds to determine that nothing changed.
    if ":" not in attr:
        # If the flake is changed, the mandala cache is invalid
        # Therefore, make the Nix flake and lock an argument tracked by Mandala.
        path = pathlib.Path(attr.partition("#")[0])
        ret = _cached_nix_build(
            attr,
            (path / "flake.nix").read_text(),
            json.loads((path / "flake.lock").read_text()),
        )
    else:
        ret = _cached_nix_build(attr, "", None)
    return mandala.model.Context.current_context.storage.unwrap(ret)


@op
def _cached_nix_build(attr: str, flake_src: str, flake_lock: typing.Any) -> str:
    print(f"Nix building {attr}")
    cmd = ["nix", "build", attr, "--print-out-paths", "--no-link"]
    proc = measure_resources.measure_resources(cmd)
    print(f"Done in {proc.walltime.total_seconds():.1f}sec")
    proc.raise_for_error()
    ret = proc.stdout.decode().strip()
    return ret


@dataclasses.dataclass(frozen=True)
class Variable:
    name: str


@dataclasses.dataclass(frozen=True)
class NixAttr:
    attr: str

    def expand(self) -> str:
        return nix_build(self.attr)

    def __hash__(self) -> int:
        return int.from_bytes(hashlib.md5(self.expand().encode()).digest())

    def __eq__(self, other: typing.Any) -> bool:
        if isinstance(other, NixAttr):
            return self.expand() == other.expand()
        else:
            return False

    def __getstate__(self) -> typing.Mapping[str, str]:
        # Mandala uses joblib.hash which uses pickle to get the state of an object for hashing purposes.
        # We want to override this to depend on the state of the Nix flake as well.
        return {"expanded": self.expand()}


@dataclasses.dataclass(frozen=True)
class Combo:
    parts: typing.Sequence[str | Variable | NixAttr | pathlib.Path]

    def expand(self, context: typing.Mapping[str, str]) -> str:
        return "".join(
            part if isinstance(part, str) else
            context[part.name] if isinstance(part, Variable) else
            part.expand() if isinstance(part, NixAttr) else
            str(part) if isinstance(part, pathlib.Path) else
            util.raise_(TypeError(f"{type(part)!s}: {part!r}"))
            for part in self.parts
        )


@dataclasses.dataclass(frozen=True)
class Command:
    args: typing.Sequence[str | NixAttr | Variable | Combo]

    def expand(self, context: typing.Mapping[str, str]) -> list[str]:
        return [
            part if isinstance(part, str) else
            context[part.name] if isinstance(part, Variable) else
            part.expand() if isinstance(part, NixAttr) else
            str(part) if isinstance(part, pathlib.Path) else
            part.expand(context) if isinstance(part, Combo) else
            util.raise_(TypeError(f"{type(part)!s}: {part!r}"))
            for part in self.args
        ]

    def __bool__(self) -> bool:
        return bool(self.args)
