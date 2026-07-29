#!/usr/bin/env python
"""Compare trained runs with deep inference testing and cross-evaluation.

Each positional argument is a run directory containing a ``model.pt`` and
``metrics.json``. The script loads each model, evaluates it on multiple test
datasets, and produces extensive comparison artifacts.

Examples
--------
    python compare.py artifacts/runs/*/ --output-dir artifacts/comparison

    python compare.py runs/baseline runs/attn --test-data data/eng-fra.txt_clean
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import torch

from seq2seq.data import (
    EOS_token,
    Lang,
    build_dataset,
    indexes_from_sentence,
    make_pair_filter,
    prepare_data,
    read_langs,
    tensor_from_sentence,
)
from seq2seq.experiment import LoadedModel, TrainConfig, load_checkpoint
from seq2seq.io_utils import ensure_dir, load_json, save_json
from seq2seq.plotting import (
    plot_comparison_bars,
    plot_comparison_curves,
    plot_grouped_bars,
    plot_length_histogram,
    plot_losses,
)
from seq2seq.models import build_model, resolve_hidden_size
from seq2seq.train import evaluate, evaluate_accuracy, evaluate_loss
from seq2seq.text import normalize_string
from seq2seq.utils import resolve_device, set_seed

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
    "bleu",
    "bleu_1",
    "bleu_2",
    "bleu_3",
    "bleu_4",
    "token_precision",
    "token_recall",
    "token_f1",
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
        help="Run directories, each containing model.pt and metrics.json. "
        "The directory name is used as the model name.",
    )
    p.add_argument("--output-dir", default="artifacts/comparison", help="Comparison directory.")
    p.add_argument(
        "--test-data",
        nargs="*",
        default=None,
        help="Optional clean data files to run fresh inference on.",
    )
    p.add_argument(
        "--inference-limit",
        type=int,
        default=2000,
        help="Max pairs to evaluate per model per dataset.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility.",
    )
    return p


def load_run(run_dir: str) -> dict:
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
        models, values("bleu"), os.path.join(out_dir, "cmp_bleu.png"),
        ylabel="BLEU-4", title="BLEU score by model",
    )
    plot_comparison_bars(
        models, values("token_f1"), os.path.join(out_dir, "cmp_token_f1.png"),
        ylabel="token F1", title="Token F1 by model",
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


def load_pairs_from_file(path: str) -> List[Tuple[str, str]]:
    """Load tab-separated language pairs from a clean data file."""
    pairs: List[Tuple[str, str]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                pairs.append((normalize_string(parts[0]), normalize_string(parts[1])))
    return pairs


def filter_pairs(pairs: List[Tuple[str, str]], max_length: int, use_prefix: bool) -> List[Tuple[str, str]]:
    pf = ["i m", "he s", "she s", "you re", "we re", "they re"] if use_prefix else None
    filt = make_pair_filter(max_length, pf)
    return [p for p in pairs if filt(list(p))]


def run_deep_inference(
    loaded: LoadedModel,
    test_pairs: List[Tuple[str, str]],
    limit: int,
    max_lengths: List[int],
    device: torch.device,
) -> Dict[str, dict]:
    """Run evaluate_accuracy at multiple max_lengths and collect per-model metrics."""
    results: Dict[str, dict] = {}

    for ml in max_lengths:
        filtered = filter_pairs(test_pairs, ml, use_prefix=False)
        if not filtered:
            continue
        sample = random.sample(filtered, min(limit, len(filtered)))
        metrics = evaluate_accuracy(
            loaded.encoder,
            loaded.decoder,
            sample,
            loaded.input_lang,
            loaded.output_lang,
            device,
            limit=None,
        )
        results[f"len{ml}"] = metrics

    return results


def run_loss_evaluation(
    loaded: LoadedModel,
    raw_pairs: List[Tuple[str, str]],
    max_length: int,
    batch_size: int,
    device: torch.device,
) -> float:
    """Build a dataloader from pairs and compute NLL loss via evaluate_loss."""
    import torch.nn as nn
    from seq2seq.data import _pad_ids, indexes_from_sentence

    filtered = filter_pairs(raw_pairs, max_length, use_prefix=False)
    if not filtered:
        return float("inf")

    filtered_as_lists = [[p[0], p[1]] for p in filtered]
    input_ids, target_ids = _pad_ids(filtered_as_lists, loaded.input_lang, loaded.output_lang, max_length)
    dataset = torch.utils.data.TensorDataset(
        torch.LongTensor(input_ids).to(device),
        torch.LongTensor(target_ids).to(device),
    )
    loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size)
    criterion = nn.NLLLoss()
    return evaluate_loss(loader, loaded.encoder, loaded.decoder, criterion)


def extract_attention_samples(
    loaded: LoadedModel,
    test_pairs: List[Tuple[str, str]],
    out_dir: str,
    max_length: int,
    n_samples: int,
    device: torch.device,
) -> List[str]:
    """Generate per-model attention heatmaps for sample sentences."""
    from seq2seq.plotting import plot_attention

    filtered = filter_pairs(test_pairs, max_length, use_prefix=True)
    if not filtered:
        return []
    samples = random.sample(filtered, min(n_samples, len(filtered)))

    files: List[str] = []
    for i, (src, tgt) in enumerate(samples):
        try:
            words, attns = evaluate(
                loaded.encoder, loaded.decoder,
                src, loaded.input_lang, loaded.output_lang, device,
            )
        except KeyError:
            continue
        if attns is None:
            break
        path = os.path.join(out_dir, f"attn_{loaded.config.run_name}_{i}.png")
        plot_attention(src, words, attns[0, :len(words), :], path)
        attrs_dumped = [
            f"\n--- Attention sample {i} ---",
            f"Input:  {src}",
            f"Gold:   {tgt}",
            f"Output: {' '.join(words)}",
        ]
        files.append(os.path.basename(path))
        with open(os.path.join(out_dir, f"attn_{loaded.config.run_name}_{i}.txt"), "w") as fh:
            fh.write("\n".join([os.path.basename(path)] + attrs_dumped) + "\n")
    return files


def main() -> None:
    args = build_parser().parse_args()
    set_seed(args.seed)
    device = resolve_device()

    out_dir = ensure_dir(args.output_dir)

    results = [load_run(d) for d in args.run_dirs]

    names = [r["model"] for r in results]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        print(f"WARNING: duplicate model names: {sorted(duplicates)}", file=sys.stderr)

    results.sort(key=_val_loss_key)

    # --- Static comparison (metrics.json only) ---
    write_table(results, out_dir)
    write_charts(results, out_dir)

    # --- Deep inference: load models and run cross-evaluation ---
    print("\n=== Loading models for deep inference ===")
    loaded_models: List[LoadedModel] = []
    for r in results:
        ckpt_path = os.path.join(r["run_dir"], "model.pt")
        if not os.path.isfile(ckpt_path):
            print(f"  SKIP {r['model']}: no model.pt found")
            continue
        lm = load_checkpoint(ckpt_path, device=str(device))
        loaded_models.append(lm)
        print(f"  Loaded {r['model']} ({lm.config.arch}, h={lm.hidden_size}, "
              f"params={r.get('n_params')})")

    if not loaded_models:
        print("No models to evaluate. Done.")
        return

    # --- Load test data files ---
    test_data_files: List[str] = args.test_data or []
    if not test_data_files:
        # Auto-discover clean data files near the first run dir
        data_dir = os.path.join(results[0]["run_dir"], "..", "..", "data")
        data_dir = os.path.normpath(data_dir)
        if os.path.isdir(data_dir):
            for f in sorted(os.listdir(data_dir)):
                if f.endswith(".txt_clean") or f.endswith(".txt"):
                    test_data_files.append(os.path.join(data_dir, f))

    all_test_pairs: Dict[str, List[Tuple[str, str]]] = {}
    for path in test_data_files:
        if os.path.isfile(path):
            pairs = load_pairs_from_file(path)
            if pairs:
                label = os.path.basename(path).replace(".txt_clean", "").replace(".txt", "")
                all_test_pairs[label] = pairs
                print(f"  Test data: {label} ({len(pairs)} pairs)")

    if not all_test_pairs:
        print("No test data found, skipping deep inference.")
    else:
        # --- Cross-evaluation: each model on each dataset ---
        print(f"\n=== Cross-evaluation ({args.inference_limit} pairs/model/dataset) ===")
        max_lengths = [10, 15, 20]

        cross_results: Dict[str, Dict[str, dict]] = defaultdict(dict)
        for lm in loaded_models:
            model_name = os.path.basename(lm.config.run_name or "unknown")
            for ds_label, test_pairs in all_test_pairs.items():
                print(f"  Evaluating {model_name} on {ds_label} ...")
                deep = run_deep_inference(lm, test_pairs, args.inference_limit, max_lengths, device)
                cross_results[model_name][ds_label] = deep

        # --- Cross-evaluation artifact: grouped bar charts per metric ---
        datasets = sorted(all_test_pairs.keys())
        model_names = [os.path.basename(lm.config.run_name or "unknown") for lm in loaded_models]

        for ml in max_lengths:
            key = f"len{ml}"
            for metric in ["word_accuracy", "bleu", "token_f1", "exact_match"]:
                series: Dict[str, List[float]] = defaultdict(list)
                group_labels: List[str] = []
                for ds in datasets:
                    group_labels.append(ds)
                    for mn in model_names:
                        entry = cross_results.get(mn, {}).get(ds, {}).get(key, {})
                        val = entry.get(metric, 0.0)
                        series.setdefault(mn, []).append(float(val))
                if any(any(v != 0 for v in vals) for vals in series.values()):
                    plot_grouped_bars(
                        group_labels,
                        series,
                        os.path.join(out_dir, f"cross_{metric}_{key}.png"),
                        ylabel=metric.replace("_", " "),
                        title=f"Cross-eval {metric} (max_length={ml})",
                    )

        # --- Save cross-evaluation JSON ---
        save_json(
            {mn: {ds: v for ds, v in datasets.items()} for mn, datasets in cross_results.items()},
            os.path.join(out_dir, "cross_evaluation.json"),
        )

        # --- Per-model loss on each dataset ---
        print(f"\n=== Loss evaluation on test data ===")
        loss_results: Dict[str, Dict[str, float]] = {}
        for lm in loaded_models:
            model_name = os.path.basename(lm.config.run_name or "unknown")
            loss_results[model_name] = {}
            for ds_label, test_pairs in all_test_pairs.items():
                loss_val = run_loss_evaluation(lm, test_pairs, max_length=lm.decoder.max_length, batch_size=64, device=device)
                loss_results[model_name][ds_label] = loss_val
                print(f"  {model_name} on {ds_label}: loss={loss_val:.4f}")

        # Plot cross-evaluation loss bars
        for ds_label in datasets:
            vals = [loss_results.get(mn, {}).get(ds_label, 0.0) for mn in model_names]
            plot_comparison_bars(
                model_names,
                vals,
                os.path.join(out_dir, f"cross_loss_{ds_label}.png"),
                ylabel="NLL loss",
                title=f"Cross-eval NLL loss on {ds_label}",
            )

        save_json(loss_results, os.path.join(out_dir, "loss_evaluation.json"))

        # --- Per-sentence attention heatmaps for each model ---
        print(f"\n=== Generating attention heatmaps ===")
        all_pairs = []
        for pairs in all_test_pairs.values():
            all_pairs.extend(pairs)
        if all_pairs:
            for lm in loaded_models:
                extract_attention_samples(
                    lm, all_pairs, out_dir, max_length=lm.decoder.max_length, n_samples=5, device=device,
                )

        # --- Per-model loss curve re-plot (individual, high-res) ---
        print(f"\n=== Individual loss curves ===")
        for r in results:
            train_curve = r.get("train_loss_curve")
            val_curve = r.get("val_loss_curve")
            if train_curve or val_curve:
                plot_losses(
                    train_curve or [],
                    val_curve or [],
                    os.path.join(out_dir, f"loss_{r['model']}.png"),
                    title=f"Loss curve: {r['model']}",
                )

        # --- Length distribution analysis ---
        print(f"\n=== Length distribution analysis ===")
        for ds_label, pairs in all_test_pairs.items():
            lengths_in = [len(p[0].split()) for p in pairs[:5000]]
            lengths_out = [len(p[1].split()) for p in pairs[:5000]]
            plot_length_histogram(
                {"input": lengths_in, "output": lengths_out},
                os.path.join(out_dir, f"len_dist_{ds_label}.png"),
                title=f"Sentence length distribution: {ds_label}",
            )

    # --- Final summary ---
    best = max(results, key=lambda r: r.get("bleu") or 0.0)
    print(
        f"\nBest by BLEU: {best['model']} "
        f"(bleu={best.get('bleu')}, word_acc={best.get('word_accuracy')}, "
        f"val_loss={best.get('final_val_loss')})"
    )
    print(f"Compared {len(results)} run(s); artifacts written to: {out_dir}")


if __name__ == "__main__":
    main()
