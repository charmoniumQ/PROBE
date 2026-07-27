#!/usr/bin/env python
"""Evaluate a single trained seq2seq checkpoint.

Loads a ``model.pt`` produced by ``train.py`` and, depending on the flags:

* scores it on a data split (NLL loss, word accuracy, exact-match),
* dumps sample translations,
* renders attention maps (attention architectures only),
* translates one sentence (``--translate``) or runs an interactive prompt
  (``--interactive``).

Examples
--------
    python evaluate.py --run-dir artifacts/eng-fra-rev_bahdanau_small
    python evaluate.py --checkpoint artifacts/.../model.pt --split val
    python evaluate.py --run-dir artifacts/... --translate "je suis fatigue ."
    python evaluate.py --run-dir artifacts/... --interactive
"""
from __future__ import annotations

import argparse
import os
from typing import List, Optional, Tuple

import torch.nn as nn

from seq2seq.data import build_dataset, normalize_string
from seq2seq.experiment import LoadedModel, load_checkpoint
from seq2seq.plotting import plot_attention
from seq2seq.train import evaluate, evaluate_accuracy, evaluate_loss
from seq2seq.utils import ensure_dir, save_json, set_seed


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Evaluate a single trained model.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    loc = p.add_mutually_exclusive_group(required=True)
    loc.add_argument("--checkpoint", default=None, help="Path to a model.pt file.")
    loc.add_argument("--run-dir", default=None, help="Run directory containing model.pt.")

    p.add_argument("--device", default=None, help="cpu / cuda / auto.")
    p.add_argument("--data-dir", default=None, help="Override data directory for scoring.")
    p.add_argument(
        "--split",
        choices=["val", "train"],
        default="val",
        help="Which split to score on.",
    )
    p.add_argument("--acc-limit", type=int, default=1000, help="Max pairs for accuracy calc.")
    p.add_argument("--n-samples", type=int, default=10, help="#sample translations to print.")
    p.add_argument(
        "--sentences",
        nargs="*",
        default=[],
        help="Source sentences to translate and render attention maps for.",
    )
    p.add_argument("--translate", default=None, help="Translate a single sentence and exit.")
    p.add_argument("--interactive", action="store_true", help="Interactive translation prompt.")
    p.add_argument("--output-dir", default=None, help="Where to write eval artifacts.")
    p.add_argument("--no-score", action="store_true", help="Skip dataset scoring.")
    return p


def resolve_checkpoint(args: argparse.Namespace) -> str:
    if args.checkpoint:
        path = args.checkpoint
    else:
        path = os.path.join(args.run_dir, "model.pt")
    if not os.path.exists(path):
        raise SystemExit(f"Checkpoint not found: {path}")
    return path


def translate(loaded: LoadedModel, sentence: str) -> Optional[List[str]]:
    """Normalise and greedily translate a sentence. Returns words or None (OOV)."""
    normalized = normalize_string(sentence)
    try:
        words, _ = evaluate(
            loaded.encoder,
            loaded.decoder,
            normalized,
            loaded.input_lang,
            loaded.output_lang,
            loaded.device,
        )
    except KeyError as exc:
        print(f"  ! out-of-vocabulary token {exc}; cannot translate.")
        return None
    return words


def run_interactive(loaded: LoadedModel) -> None:
    print("\nInteractive mode. Type a sentence to translate (blank line or Ctrl-D to quit).")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            print()
            break
        if not line:
            break
        words = translate(loaded, line)
        if words is not None:
            print("<", " ".join(words))


def score_dataset(args: argparse.Namespace, loaded: LoadedModel, out_dir: str) -> Tuple[dict, object]:
    cfg = loaded.config
    data_dir = args.data_dir or cfg.data_dir

    # Reproduce the same split the model was trained with.
    set_seed(cfg.seed)
    bundle = build_dataset(
        lang1=cfg.lang1,
        lang2=cfg.lang2,
        data_dir=data_dir,
        reverse=cfg.reverse,
        max_length=cfg.max_length,
        batch_size=cfg.batch_size,
        val_split=cfg.val_split,
        use_prefix_filter=cfg.use_prefix_filter,
        max_pairs=cfg.max_pairs,
        device=loaded.device,
    )

    if args.split == "train":
        loader = bundle.train_loader
        pairs = bundle.train_pairs
    else:
        loader = bundle.val_loader
        pairs = bundle.val_pairs

    criterion = nn.NLLLoss()
    loss = evaluate_loss(loader, loaded.encoder, loaded.decoder, criterion)
    acc_metrics = evaluate_accuracy(
        loaded.encoder,
        loaded.decoder,
        pairs,
        bundle.input_lang,
        bundle.output_lang,
        loaded.device,
        limit=args.acc_limit,
    )
    word_acc = acc_metrics["word_accuracy"]
    exact = acc_metrics["exact_match"]
    bleu = acc_metrics["bleu"]
    bleu_1 = acc_metrics["bleu_1"]
    bleu_2 = acc_metrics["bleu_2"]
    bleu_3 = acc_metrics["bleu_3"]
    bleu_4 = acc_metrics["bleu_4"]
    token_f1 = acc_metrics["token_f1"]
    token_precision = acc_metrics["token_precision"]
    token_recall = acc_metrics["token_recall"]

    sample_lines: List[str] = []
    n = min(args.n_samples, len(pairs))
    for src, tgt in pairs[:n]:
        words, _ = evaluate(
            loaded.encoder, loaded.decoder, src, bundle.input_lang, bundle.output_lang, loaded.device
        )
        sample_lines += [f"> {src}", f"= {tgt}", f"< {' '.join(words)}", ""]
    with open(os.path.join(out_dir, "eval_samples.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(sample_lines))

    metrics = {
        "checkpoint": args.checkpoint or os.path.join(args.run_dir, "model.pt"),
        "arch": cfg.arch,
        "hidden_size": loaded.hidden_size,
        "lang1": cfg.lang1,
        "lang2": cfg.lang2,
        "reverse": cfg.reverse,
        "split": args.split,
        "n_pairs": len(pairs),
        "loss": round(loss, 4),
        "word_accuracy": word_acc,
        "exact_match": exact,
        "bleu": bleu,
        "bleu_1": bleu_1,
        "bleu_2": bleu_2,
        "bleu_3": bleu_3,
        "bleu_4": bleu_4,
        "token_f1": token_f1,
        "token_precision": token_precision,
        "token_recall": token_recall,
    }
    save_json(metrics, os.path.join(out_dir, "eval_metrics.json"))
    return metrics, bundle


def render_attention(loaded: LoadedModel, sentences: List[str], out_dir: str) -> List[str]:
    files: List[str] = []
    for i, sentence in enumerate(sentences):
        normalized = normalize_string(sentence)
        try:
            words, attentions = evaluate(
                loaded.encoder,
                loaded.decoder,
                normalized,
                loaded.input_lang,
                loaded.output_lang,
                loaded.device,
            )
        except KeyError as exc:
            print(f"  ! skipping '{sentence}' (out-of-vocabulary token {exc})")
            continue
        print(f"> {normalized}\n< {' '.join(words)}")
        if attentions is None:
            print("  (model has no attention; skipping attention map)")
            continue
        path = os.path.join(out_dir, f"eval_attention_{i}.png")
        plot_attention(normalized, words, attentions[0, : len(words), :], path)
        files.append(path)
    return files


def main() -> None:
    args = build_parser().parse_args()
    ckpt_path = resolve_checkpoint(args)
    loaded = load_checkpoint(ckpt_path, device=args.device)

    default_out = args.run_dir or os.path.dirname(ckpt_path) or "."
    out_dir = ensure_dir(args.output_dir or os.path.join(default_out, "eval"))
    print(
        f"Loaded {loaded.config.arch} model (hidden={loaded.hidden_size}, "
        f"{loaded.config.lang1}->{loaded.config.lang2}"
        f"{' reversed' if loaded.config.reverse else ''}) on {loaded.device}"
    )

    if args.translate is not None:
        words = translate(loaded, args.translate)
        if words is not None:
            print("<", " ".join(words))
        return

    if args.interactive:
        run_interactive(loaded)
        return

    if not args.no_score:
        metrics, _ = score_dataset(args, loaded, out_dir)
        print(
            f"\n[{metrics['split']}] loss={metrics['loss']} "
            f"word_acc={metrics['word_accuracy']} exact={metrics['exact_match']} "
            f"bleu={metrics['bleu']} f1={metrics['token_f1']} "
            f"({metrics['n_pairs']} pairs)"
        )

    if args.sentences:
        print("\nAttention / translations:")
        render_attention(loaded, args.sentences, out_dir)

    print(f"\nEval artifacts written to: {out_dir}")


if __name__ == "__main__":
    main()
