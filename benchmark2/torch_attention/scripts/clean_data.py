#!/usr/bin/env python
"""Clean a raw ``lang1-lang2`` translation file.

Anki / Tatoeba exports are tab-separated and often contain a trailing
attribution column, duplicates, blank sides and very long sentences. This
script produces a cleaned two-column ``<src>\\t<tgt>`` file plus a JSON report
and a length-distribution plot.

Example
-------
Clean the bundled English/French file, keeping pairs up to 15 words::

    python clean_data.py --lang1 eng --lang2 fra --max-length 15

    # explicit paths
    python clean_data.py --input data/eng-fra.txt --output data/eng-fra.clean.txt
"""
from __future__ import annotations

import argparse
import os
from collections import Counter
from io import open
from typing import List, Optional, Tuple

from seq2seq.text import normalize_string
from seq2seq.plotting import plot_length_histogram
from seq2seq.io_utils import ensure_dir, save_json

Pair = Tuple[str, str]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Clean a raw language-pair file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    src = p.add_argument_group("input location")
    src.add_argument("--input", default=None, help="Explicit path to the raw file.")
    src.add_argument("--lang1", default="eng", help="Used to locate <l1>-<l2>.txt.")
    src.add_argument("--lang2", default="fra", help="Used to locate <l1>-<l2>.txt.")
    src.add_argument("--data-dir", default="data", help="Directory holding the raw file.")

    out = p.add_argument_group("output")
    out.add_argument("--output", default=None, help="Cleaned file path (default: *.clean.txt).")
    out.add_argument("--report-dir", default="artifacts/clean", help="Where to write report + plot.")

    filt = p.add_argument_group("cleaning options")
    filt.add_argument("--max-length", type=int, default=None, help="Drop pairs longer than N words (either side).")
    filt.add_argument("--min-length", type=int, default=1, help="Drop pairs shorter than N words (either side).")
    filt.add_argument(
        "--normalize",
        action="store_true",
        help="Apply the training-time normalisation (lowercase, ASCII, strip punctuation).",
    )
    filt.add_argument(
        "--lowercase",
        action="store_true",
        help="Lowercase both sides (implied by --normalize).",
    )
    filt.add_argument(
        "--dedupe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Drop duplicate pairs.",
    )
    filt.add_argument(
        "--drop-identical",
        action="store_true",
        help="Drop pairs whose two sides are identical.",
    )
    return p


def resolve_paths(args: argparse.Namespace) -> Tuple[str, str]:
    if args.input:
        input_path = args.input
    else:
        input_path = os.path.join(args.data_dir, f"{args.lang1}-{args.lang2}.txt")
    if args.output:
        output_path = args.output
    else:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}.clean{ext or '.txt'}"
    return input_path, output_path


def clean_side(text: str, normalize: bool, lowercase: bool) -> str:
    text = text.strip()
    if normalize:
        return normalize_string(text)
    # Collapse internal whitespace even without full normalisation.
    text = " ".join(text.split())
    if lowercase:
        text = text.lower()
    return text


def clean(
    input_path: str,
    output_path: str,
    max_length: Optional[int],
    min_length: int,
    normalize: bool,
    lowercase: bool,
    dedupe: bool,
    drop_identical: bool,
) -> dict:
    stats = Counter()
    seen: set = set()
    kept: List[Pair] = []

    with open(input_path, encoding="utf-8") as fh:
        for line in fh:
            stats["total_lines"] += 1
            line = line.rstrip("\n")
            if not line.strip():
                stats["dropped_blank_line"] += 1
                continue

            fields = line.split("\t")
            if len(fields) < 2:
                stats["dropped_malformed"] += 1
                continue

            # Keep only the first two columns (drop attribution, etc.).
            src = clean_side(fields[0], normalize, lowercase)
            tgt = clean_side(fields[1], normalize, lowercase)

            if not src or not tgt:
                stats["dropped_empty_side"] += 1
                continue

            src_len = len(src.split(" "))
            tgt_len = len(tgt.split(" "))
            if src_len < min_length or tgt_len < min_length:
                stats["dropped_too_short"] += 1
                continue
            if max_length is not None and (src_len > max_length or tgt_len > max_length):
                stats["dropped_too_long"] += 1
                continue

            if drop_identical and src == tgt:
                stats["dropped_identical"] += 1
                continue

            if dedupe:
                key = (src, tgt)
                if key in seen:
                    stats["dropped_duplicate"] += 1
                    continue
                seen.add(key)

            kept.append((src, tgt))
            stats["kept"] += 1

    ensure_dir(os.path.dirname(output_path) or ".")
    with open(output_path, "w", encoding="utf-8") as fh:
        for src, tgt in kept:
            fh.write(f"{src}\t{tgt}\n")

    src_lengths = [len(s.split(" ")) for s, _ in kept]
    tgt_lengths = [len(t.split(" ")) for _, t in kept]

    def summarize(lengths: List[int]) -> dict:
        if not lengths:
            return {"min": 0, "max": 0, "mean": 0.0}
        return {
            "min": min(lengths),
            "max": max(lengths),
            "mean": round(sum(lengths) / len(lengths), 2),
        }

    return {
        "input_path": input_path,
        "output_path": output_path,
        "counts": dict(stats),
        "kept": len(kept),
        "src_length": summarize(src_lengths),
        "tgt_length": summarize(tgt_lengths),
        "_src_lengths": src_lengths,
        "_tgt_lengths": tgt_lengths,
    }


def main() -> None:
    args = build_parser().parse_args()
    input_path, output_path = resolve_paths(args)
    if not os.path.exists(input_path):
        raise SystemExit(f"Input file not found: {input_path}")

    normalize = args.normalize
    lowercase = args.lowercase or args.normalize

    print(f"Cleaning {input_path} -> {output_path}")
    report = clean(
        input_path=input_path,
        output_path=output_path,
        max_length=args.max_length,
        min_length=args.min_length,
        normalize=normalize,
        lowercase=lowercase,
        dedupe=args.dedupe,
        drop_identical=args.drop_identical,
    )

    report_dir = ensure_dir(args.report_dir)
    src_lengths = report.pop("_src_lengths")
    tgt_lengths = report.pop("_tgt_lengths")

    if src_lengths:
        plot_length_histogram(
            {"source": src_lengths, "target": tgt_lengths},
            os.path.join(report_dir, "length_distribution.png"),
            title=f"Length distribution ({os.path.basename(output_path)})",
        )
    save_json(report, os.path.join(report_dir, "clean_report.json"))

    print("\nCleaning summary:")
    for key, value in report["counts"].items():
        print(f"  {key:22s} {value}")
    print(f"  {'kept':22s} {report['kept']}")
    print(f"\nSource length: {report['src_length']}")
    print(f"Target length: {report['tgt_length']}")
    print(f"\nCleaned file: {output_path}")
    print(f"Report + plot: {report_dir}")


if __name__ == "__main__":
    main()
