#!/usr/bin/env python
"""Verify that two language-pair datasets are indistinguishable after cleaning.

Different raw sources look nothing alike: ``data/eng-fra.txt`` has two columns
and French diacritics, while an Anki export such as ``data/eng-spa.txt`` has a
third attribution column, Spanish accents and inverted punctuation. Once both
are pushed through the canonical preprocessing (:func:`seq2seq.data.normalize_string`
plus keeping only the first two columns) every dataset-specific *format*
fingerprint disappears -- only the genuine linguistic content differs.

This script canonicalises both files with identical settings and then compares
their **format fingerprints**. If no format feature distinguishes them, a
format-based classifier has zero signal, so the datasets are indistinguishable
in form. It writes a JSON report, an overlaid length-distribution plot and a
shuffled "blind" sample mixing lines from both.

Example
-------
    python verify_datasets.py data/eng-fra.txt data/eng-spa.txt --max-length 10
"""
from __future__ import annotations

import argparse
import os
import random
import string
from io import open
from typing import Dict, List, Tuple

from seq2seq.text import CANONICAL_ALPHABET, is_canonical, normalize_string
from seq2seq.plotting import plot_length_histogram
from seq2seq.io_utils import ensure_dir, save_json

Pair = Tuple[str, str]
OTHER_PUNCT = set(string.punctuation) - {"!", "?"}

# Format features compared across datasets. After canonicalisation every one of
# these should hold the same (usually falsy) value for both datasets.
SCHEMA_KEYS = [
    "n_columns",
    "has_uppercase",
    "has_digit",
    "has_non_ascii",
    "has_other_punct",
    "has_double_space",
    "has_edge_space",
    "charset_within_canonical",
    "all_sides_canonical",
]


def char_flags(text: str) -> Dict[str, bool]:
    return {
        "has_uppercase": any(c.isupper() for c in text),
        "has_digit": any(c.isdigit() for c in text),
        "has_non_ascii": any(ord(c) > 127 for c in text),
        "has_other_punct": any(c in OTHER_PUNCT for c in text),
    }


def read_raw_lines(path: str, sample: int | None) -> List[str]:
    lines = open(path, encoding="utf-8").read().splitlines()
    lines = [ln for ln in lines if ln.strip()]
    if sample and len(lines) > sample:
        lines = random.sample(lines, sample)
    return lines


def raw_fingerprint(lines: List[str]) -> Dict[str, object]:
    """Fingerprint of the *raw* file (before preprocessing)."""
    max_cols = 0
    agg = {"has_uppercase": False, "has_digit": False, "has_non_ascii": False, "has_other_punct": False}
    for ln in lines:
        cols = ln.split("\t")
        max_cols = max(max_cols, len(cols))
        pair_text = " ".join(cols[:2])  # inspect the translation pair, not attribution
        for k, v in char_flags(pair_text).items():
            agg[k] = agg[k] or v
    return {"n_columns": max_cols, **agg}


def canonicalise(lines: List[str], max_length: int | None) -> List[Pair]:
    pairs: List[Pair] = []
    for ln in lines:
        cols = ln.split("\t")
        if len(cols) < 2:
            continue
        src = normalize_string(cols[0])
        tgt = normalize_string(cols[1])
        if not src or not tgt:
            continue
        if max_length is not None:
            if len(src.split(" ")) > max_length or len(tgt.split(" ")) > max_length:
                continue
        pairs.append((src, tgt))
    return pairs


def clean_fingerprint(pairs: List[Pair]) -> Dict[str, object]:
    """Fingerprint of the dataset *after* canonical preprocessing."""
    sides = [s for pair in pairs for s in pair]
    charset = set().union(*[set(s) for s in sides]) if sides else set()
    agg = {"has_uppercase": False, "has_digit": False, "has_non_ascii": False, "has_other_punct": False}
    for s in sides:
        for k, v in char_flags(s).items():
            agg[k] = agg[k] or v
    conformance = sum(is_canonical(s) for s in sides) / max(len(sides), 1)
    return {
        "n_columns": 2,
        **agg,
        "has_double_space": any("  " in s for s in sides),
        "has_edge_space": any(s != s.strip() for s in sides),
        "charset_within_canonical": charset <= set(CANONICAL_ALPHABET),
        "all_sides_canonical": conformance == 1.0,
        "_charset": "".join(sorted(charset)),
        "_conformance": round(conformance, 6),
    }


def length_stats(pairs: List[Pair]) -> Dict[str, object]:
    src = [len(s.split(" ")) for s, _ in pairs]
    tgt = [len(t.split(" ")) for _, t in pairs]

    def summ(xs: List[int]) -> Dict[str, float]:
        return {
            "min": min(xs) if xs else 0,
            "max": max(xs) if xs else 0,
            "mean": round(sum(xs) / len(xs), 2) if xs else 0.0,
        }

    return {"n_pairs": len(pairs), "src_tokens": summ(src), "tgt_tokens": summ(tgt)}


def differing_keys(fa: Dict[str, object], fb: Dict[str, object], keys: List[str]) -> List[str]:
    return [k for k in keys if fa.get(k) != fb.get(k)]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Verify two datasets are format-indistinguishable after cleaning.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("file_a", help="First raw dataset (e.g. data/eng-fra.txt).")
    p.add_argument("file_b", help="Second raw dataset (e.g. data/eng-spa.txt).")
    p.add_argument("--max-length", type=int, default=10, help="Shared max sentence length filter.")
    p.add_argument("--sample", type=int, default=None, help="Optionally sample N raw lines per file.")
    p.add_argument("--report-dir", default="artifacts/verify", help="Where to write report + plot.")
    p.add_argument("--seed", type=int, default=1, help="Sampling/shuffle seed.")
    return p


def main() -> None:
    args = build_parser().parse_args()
    random.seed(args.seed)
    for path in (args.file_a, args.file_b):
        if not os.path.exists(path):
            raise SystemExit(f"File not found: {path}")

    name_a = os.path.splitext(os.path.basename(args.file_a))[0]
    name_b = os.path.splitext(os.path.basename(args.file_b))[0]

    raw_a = read_raw_lines(args.file_a, args.sample)
    raw_b = read_raw_lines(args.file_b, args.sample)

    raw_fp_a, raw_fp_b = raw_fingerprint(raw_a), raw_fingerprint(raw_b)
    pairs_a = canonicalise(raw_a, args.max_length)
    pairs_b = canonicalise(raw_b, args.max_length)
    clean_fp_a, clean_fp_b = clean_fingerprint(pairs_a), clean_fingerprint(pairs_b)

    raw_diff = differing_keys(raw_fp_a, raw_fp_b, ["n_columns", "has_uppercase", "has_digit", "has_non_ascii", "has_other_punct"])
    clean_diff = differing_keys(clean_fp_a, clean_fp_b, SCHEMA_KEYS)

    both_canonical = bool(clean_fp_a["all_sides_canonical"] and clean_fp_b["all_sides_canonical"])
    both_within = bool(clean_fp_a["charset_within_canonical"] and clean_fp_b["charset_within_canonical"])
    indistinguishable = (len(clean_diff) == 0) and both_canonical and both_within

    report_dir = ensure_dir(args.report_dir)
    report = {
        "file_a": args.file_a,
        "file_b": args.file_b,
        "max_length": args.max_length,
        "raw_fingerprint": {name_a: raw_fp_a, name_b: raw_fp_b},
        "raw_distinguishing_features": raw_diff,
        "clean_fingerprint": {name_a: clean_fp_a, name_b: clean_fp_b},
        "clean_distinguishing_features": clean_diff,
        "length_stats": {name_a: length_stats(pairs_a), name_b: length_stats(pairs_b)},
        "indistinguishable_after_preprocessing": indistinguishable,
    }
    save_json(report, os.path.join(report_dir, "verify_report.json"))

    # Overlaid length distribution (combined src+tgt token counts per dataset).
    plot_length_histogram(
        {
            name_a: [len(s.split(" ")) for pair in pairs_a for s in pair],
            name_b: [len(s.split(" ")) for pair in pairs_b for s in pair],
        },
        os.path.join(report_dir, "length_distribution.png"),
        title="Token-length distribution after preprocessing",
    )

    # Blind sample: shuffled canonical lines from both, so format alone gives
    # no clue which dataset a line came from.
    blind = [f"{s}\t{t}" for s, t in random.sample(pairs_a, min(15, len(pairs_a)))]
    blind += [f"{s}\t{t}" for s, t in random.sample(pairs_b, min(15, len(pairs_b)))]
    random.shuffle(blind)
    with open(os.path.join(report_dir, "blind_sample.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(blind))

    # ---- Report ----
    print(f"\nRaw fingerprints (before preprocessing):")
    print(f"  {name_a}: {raw_fp_a}")
    print(f"  {name_b}: {raw_fp_b}")
    print(f"  -> distinguishing raw format features: {raw_diff or 'none'}")

    print(f"\nClean fingerprints (after preprocessing):")
    for name, fp in ((name_a, clean_fp_a), (name_b, clean_fp_b)):
        schema = {k: fp[k] for k in SCHEMA_KEYS}
        print(f"  {name}: {schema}")
    print(f"  -> distinguishing clean format features: {clean_diff or 'none'}")

    print(f"\nCanonical alphabet: {''.join(sorted(CANONICAL_ALPHABET))!r}")
    print(f"  {name_a} charset: {clean_fp_a['_charset']!r}")
    print(f"  {name_b} charset: {clean_fp_b['_charset']!r}")

    verdict = "PASS" if indistinguishable else "FAIL"
    print(f"\n[{verdict}] indistinguishable after preprocessing: {indistinguishable}")
    print(f"Report + plot + blind sample written to: {report_dir}")
    if not indistinguishable:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
