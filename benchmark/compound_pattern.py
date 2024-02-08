from __future__ import annotations
import re
import dataclasses
from collections.abc import Mapping
import util
from typing import Any


@dataclasses.dataclass
class CompoundPattern:
    """
    If the string matches an initial pattern, each captured group is then matched against
    a list of subpatterns, and so on.
    """
    pattern: re.Pattern[str]
    subpatterns: Mapping[str, list[CompoundPattern]] = dataclasses.field(default_factory=dict)
    name: str | None = None

    def match(self, candidate: str, verbose: bool = False) -> None | CompoundMatch:
        if match := self.pattern.match(candidate):
            if verbose:
                print(f"Matched {candidate!r} against root of {self.name!s}")
            submatches = {}
            for key, string in match.groupdict().items():
                if key in self.subpatterns and string is not None:
                    for subpattern in self.subpatterns[key]:
                        if string is not None and (submatch := subpattern.match(string, verbose=verbose)):
                            submatches[key] = submatch
                            break
                    else:
                        if verbose:
                            print(f"Could not match {string!r} against any {key} of {self.name!s}")
                        return None
            return CompoundMatch(self.name, match, submatches)
        else:
            if verbose:
                print(f"Could not match {candidate!r} against root of {self.name!s}")
            return None


@dataclasses.dataclass
class CompoundMatch:
    name: str | None
    match: re.Match[str]
    submatches: Mapping[str, CompoundMatch]

    def combined_groupdict(self) -> Mapping[str, str]:
        return util.merge_dicts(
            (
                self.submatches[key].combined_groupdict()
                if key in self.submatches
                else {key: string}
            )
            for key, string in self.match.groupdict().items()
            if isinstance(string, str)
        )

    def nested_groupdict(self) -> Mapping[str, Any]:
        return {
            key: (
                self.submatches[key].nested_groupdict()
                if key in self.submatches
                else string
            )
            for key, string in self.match.groupdict().items()
            if isinstance(string, str)
        }


if __name__ == "__main__":
    string = '12    connect(70, {sa_family=AF_INET, sin_port=htons(0), sin_addr=inet_addr("127.0.0.1")}, 16) = 0'
    function_name = "[a-z0-9_.]+"
    line_pattern = CompoundPattern(
        pattern=re.compile(r"^(?P<line>.*)$"),
        name="match-all",
        subpatterns={
            "line": [
                CompoundPattern(
                    name="call",
                    pattern=re.compile(r"^(?P<pid>\d+) +(?P<op>fname)\((?P<args>.*)(?:\) += (?P<ret>.*)| <unfinished ...>)$".replace("fname", function_name)),
                    subpatterns={
                        "args": [
                            CompoundPattern(
                                re.compile(r'^(?:(?P<before_args>[^"]*), )?"(?P<target0>[^"]*)", (?:(?P<between_args>[^"]*), )?"(?P<target1>[^"]*)"(?:, (?P<after_args>[^"]*))?$'),
                                name="2-str",
                            ),
                            CompoundPattern(
                                re.compile(r'^(?:(?P<before_args>[^"]*), )?"(?P<target0>[^"]*)"(?:, (?P<after_args>[^"]*))?$'),
                                name="1-str",
                            ),
                            CompoundPattern(
                                re.compile(r'^(?P<all_args>[^"]*)$'),
                                name="0-str",
                            ),
                            # Special case for execve:
                            CompoundPattern(
                                re.compile(r'^"(?P<target0>[^"]*)", (?P<after_args>\[.*\].*)$'),
                                name="execve",
                            ),
                            CompoundPattern(
                                re.compile(r"^(?P<before_struct>[^{]*), \{(?P<struct>.*?)\}, (?P<after_struct>.*)$"),
                                name="struct",
                                subpatterns={
                                    "struct": [
                                        CompoundPattern(
                                            re.compile(r'^(?:(?P<before_items>[^"]*), )?(?P<target0_key>[a-zA-Z0-9_]+)=[a-z_]*\(?"(?P<target0>[^"]*)"\)?(?:, (?P<after_items>[^"]*))?$'),
                                            name="struct-1-str",
                                        ),
                                        CompoundPattern(
                                            re.compile(r'^(?P<all_items>[^"]*)$'),
                                            name="struct-0-str",
                                        ),
                                    ],
                                }
                            ),
                        ],
                    },
                ),
                CompoundPattern(
                    re.compile(r"^(?P<pid>\d+) +<... (?P<op>fname) resumed>(?:, )?(?P<args>.*)\) += (?P<ret>.*)$".replace("fname", function_name)),
                    name="resumed",
                ),
                CompoundPattern(
                    re.compile(r"^(?P<pid>\d+) +\+\+\+ exited with (?P<exit_code>\d+) \+\+\+$"),
                    name="exit",
                ),
                CompoundPattern(
                    re.compile(r"^(?P<pid>\d+) +--- (?P<sig>SIG[A-Z0-9]+) \{(?P<sig_struct>.*)\} ---$"),
                    name="signal",
                ),
            ],
        },
    )
    match = line_pattern.match(string, verbose=True)
    assert match
    print(match.nested_groupdict())
    print(match.combined_groupdict())
