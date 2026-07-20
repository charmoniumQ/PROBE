#!/usr/bin/env python
"""Compare a set of trained runs given as a list of run directories.

Each positional argument is a run directory that contains a ``metrics.json``
(as written by ``train.py``). The **basename of the directory is used as the
model name** in the table and charts, so you control the labels simply by
naming the directories.

This script does not train anything and is torch-free -- it only reads metrics
and renders artifacts.

Examples
--------
    python compare.py artifacts/runs/*/ --output-dir artifacts/comparison

    # explicit dirs; the names 'baseline' and 'attn' become the model labels
    python compare.py runs/baseline runs/attn
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import List

from seq2seq.io_utils import ensure_dir, load_json, save_json
from seq2seq.plotting import plot_comparison_bars, plot_comparison_curves

COMPARE_COLUMNS = [
    "model",
    "arch",
    "size",
    "hidden_size",
    "n_params",
    "final_train_loss",
    "final_val_loss",
    "word_accuracy",
    "exact_match",
    "train_time_sec",
]

INF = float("inf")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compare trained runs given as a list of run directories.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "run_dirs",
        nargs="+",
        metavar="RUN_DIR",
        help="Run directories, each containing metrics.json. "
        "The directory name is used as the model name.",
    )
    p.add_argument("--output-dir", default="artifacts/comparison", help="Comparison directory.")
    return p


def load_run(run_dir: str) -> dict:
    """Load a run's metrics, tagging it with the directory basename as `model`."""
    run_dir = os.path.normpath(run_dir)
    metrics_path = os.path.join(run_dir, "metrics.json")
    if not os.path.isfile(metrics_path):
        raise SystemExit(f"No metrics.json in run directory: {run_dir}")
    metrics = dict(load_json(metrics_path))
    metrics["model"] = os.path.basename(run_dir)
    metrics["run_dir"] = run_dir
    return metrics


def _val_loss_key(result: dict) -> float:
    value = result.get("final_val_loss")
    return value if isinstance(value, (int, float)) else INF


def write_table(results: List[dict], out_dir: str) -> None:
    rows = [{col: r.get(col) for col in COMPARE_COLUMNS} for r in results]

    save_json(rows, os.path.join(out_dir, "comparison.json"))

    with open(os.path.join(out_dir, "comparison.csv"), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COMPARE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    lines = ["| " + " | ".join(COMPARE_COLUMNS) + " |"]
    lines.append("| " + " | ".join(["---"] * len(COMPARE_COLUMNS)) + " |")
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in COMPARE_COLUMNS) + " |")
    with open(os.path.join(out_dir, "comparison.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("\nComparison table:\n")
    print("\n".join(lines))


def write_charts(results: List[dict], out_dir: str) -> None:
    models = [r["model"] for r in results]

    def values(metric: str) -> List[float]:
        return [float(r.get(metric) or 0.0) for r in results]

    plot_comparison_bars(
        models, values("final_val_loss"), os.path.join(out_dir, "cmp_val_loss.png"),
        ylabel="final val NLL loss", title="Validation loss by model",
    )
    plot_comparison_bars(
        models, values("word_accuracy"), os.path.join(out_dir, "cmp_word_accuracy.png"),
        ylabel="word accuracy", title="Word accuracy by model",
    )
    plot_comparison_bars(
        models, values("n_params"), os.path.join(out_dir, "cmp_params.png"),
        ylabel="# trainable params", title="Parameter count by model",
    )
    plot_comparison_bars(
        models, values("train_time_sec"), os.path.join(out_dir, "cmp_train_time.png"),
        ylabel="train time (s)", title="Training time by model",
    )

    curves = {
        r["model"]: r.get("val_loss_curve") or r.get("train_loss_curve") or []
        for r in results
    }
    plot_comparison_curves(
        curves, os.path.join(out_dir, "cmp_loss_curves.png"),
        ylabel="val NLL loss", title="Loss curves by model",
    )


def main() -> None:
    args = build_parser().parse_args()
    out_dir = ensure_dir(args.output_dir)

    results = [load_run(d) for d in args.run_dirs]

    names = [r["model"] for r in results]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        print(f"WARNING: duplicate model names from directory basenames: {sorted(duplicates)}",
              file=sys.stderr)

    # Best (lowest) validation loss first.
    results.sort(key=_val_loss_key)

    write_table(results, out_dir)
    write_charts(results, out_dir)

    best = max(results, key=lambda r: r.get("word_accuracy") or 0.0)
    print(
        f"\nBest by word accuracy: {best['model']} "
        f"(word_acc={best.get('word_accuracy')}, val_loss={best.get('final_val_loss')})"
    )
    print(f"Compared {len(results)} run(s); artifacts written to: {out_dir}")


if __name__ == "__main__":
    main()
