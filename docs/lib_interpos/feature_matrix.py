#!/usr/bin/env python
import dataclasses
import pathlib
import enum


class RecordsData(enum.StrEnum):
    METADATA = enum.auto()
    BOTH = enum.auto()
    OPTIONAL = enum.auto()


class Bypassability(enum.StrEnum):
    BYPASSABLE_UNAWARE = enum.auto()
    BYPASSABLE_AWARE = enum.auto()
    NOT_BYPASSABLE = enum.auto()


@dataclasses.dataclass
class FeatureSet:
    user_space: bool
    no_priv: bool
    unmod_bin: bool
    bypassability: Bypassability
    coverage: str
    data: RecordsData
    replay: bool
    replay_dev: bool
    graph: bool


impls = {
    "PROBE": FeatureSet(True, True, True, Bypassability.BYPASSABLE_AWARE, "libcalls", RecordsData.OPTIONAL, True, True, True),
    "ReproZip": FeatureSet(True, True, True, Bypassability.NOT_BYPASSABLE, "syscalls", RecordsData.BOTH, True, True, True),
    "CDE, PTU, Sciunit, CARE": FeatureSet(True, True, True, Bypassability.NOT_BYPASSABLE, "syscalls", RecordsData.BOTH, True, True, False),
    "rr": FeatureSet(True, True, True, Bypassability.NOT_BYPASSABLE, "rr", RecordsData.BOTH, True, False, False),
    "strace, ltrace": FeatureSet(True, True, True, Bypassability.NOT_BYPASSABLE, "syscalls", RecordsData.METADATA, False, False, False),
    "Linux Audit": FeatureSet(True, False, True, Bypassability.NOT_BYPASSABLE, "syscalls", RecordsData.BOTH, True, False, False),
    "eBPF/CamFlow": FeatureSet(False, False, True, Bypassability.NOT_BYPASSABLE, "syscalls", RecordsData.BOTH, True, False, False),
}


labels = {
    "user_space": "User",
    "no_priv": "No priv.",
    "unmod_bin": "Unmod. bin.",
    "bypassability": "No bypass",
    "coverage": "Coverage",
    "data": "Data & metadata",
    "replay": "Replayable",
    "replay_dev": "Replay new exe.",
    "graph": "Prov. graph",
}


feature_order = [
    "user_space",
    "no_priv",
    "unmod_bin",
    "bypassability",
    # "coverage",
    "data",
    "replay",
    "replay_dev",
    "graph",
]


all_features = set(field.name for field in dataclasses.fields(FeatureSet))
assert set(feature_order) <= all_features, set(feature_order) - all_features


def latex_escape(s: str) -> str:
    for forbidden_char in "\\#_":
        if forbidden_char in s:
            raise RuntimeError(f"{forbidden_char} is in {s!r}")
    return s.replace("&", "\\&")



def get_latex_table() -> str:
    l = lambda s: latex_escape(labels.get(s, s))
    row = lambda elems: " & ".join(elems) + r" \\"
    good_color = r"\cellcolor{ForestGreen}"
    bad_color = r"\cellcolor{Mahogany}"
    med_color = r"\cellcolor{Yellow}"
    feature_converters = {
        "bypassability": lambda v: {
            Bypassability.BYPASSABLE_AWARE: bad_color,
            Bypassability.NOT_BYPASSABLE: good_color,
        }[v],
        "data": lambda v: {
            RecordsData.METADATA: med_color + "Metadata",
            RecordsData.BOTH: med_color + "Both",
            RecordsData.OPTIONAL: good_color + "Optional",
        }[v],
    }
    bool_converter = lambda v: {
        True: good_color,
        False: bad_color,
    }[v]
    return "\n".join([
        r"\begin{tabular}{c" + "c" * len(feature_order)+ "}",
        r"\toprule",
        row(["Name", *map(l, feature_order)]),
        r"\midrule",
        *[
            row([
                l(name),
                *[
                    feature_converters.get(feature, bool_converter)(getattr(features, feature))
                    for feature in feature_order
                ],
            ])
            for name, features in impls.items()
        ],
        r"\bottomrule",
        r"\end{tabular}",
    ])


if __name__ == "__main__":
    pathlib.Path("feature_matrix.tex").write_text(get_latex_table())
