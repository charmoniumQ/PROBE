#!/usr/bin/env python
"""Train a single seq2seq model on a language pair and emit artifacts.

Examples
--------
Train the default Bahdanau-attention model (French -> English)::

    python train.py --arch bahdanau --size small --epochs 40

Translate English -> French with the Luong-attention model::

    python train.py --lang1 eng --lang2 fra --no-reverse \
        --arch luong --hidden-size 256 --epochs 30

Artifacts are written to ``<output-dir>/<run-name>/``:
``loss_curve.png``, ``attention_*.png``, ``samples.txt``, ``metrics.json`` and
``model.pt``.
"""
from __future__ import annotations

import argparse

from seq2seq.experiment import TrainConfig, run_experiment
from seq2seq.models import ARCHITECTURES, SIZE_PRESETS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Train a seq2seq translation model.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    data = p.add_argument_group("data / task")
    data.add_argument("--lang1", default="eng", help="First language code (file side A).")
    data.add_argument("--lang2", default="fra", help="Second language code (file side B).")
    data.add_argument(
        "--reverse",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Translate lang2 -> lang1 (reverse the file columns).",
    )
    data.add_argument("--data-dir", default="data", help="Directory holding <l1>-<l2>.txt.")
    data.add_argument("--max-length", type=int, default=10, help="Max sentence length (words).")
    data.add_argument("--val-split", type=float, default=0.1, help="Validation fraction.")
    data.add_argument(
        "--prefix-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep only English 'I am / he is / ...' style targets (tiny dataset).",
    )
    data.add_argument("--max-pairs", type=int, default=None, help="Optional cap on #pairs.")

    model = p.add_argument_group("model")
    model.add_argument("--arch", choices=ARCHITECTURES, default="bahdanau", help="Architecture.")
    model.add_argument(
        "--size",
        choices=list(SIZE_PRESETS),
        default=None,
        help="Named hidden-size preset (overridden by --hidden-size).",
    )
    model.add_argument("--hidden-size", type=int, default=None, help="Explicit hidden size.")
    model.add_argument("--dropout", type=float, default=0.1, help="Dropout probability.")

    opt = p.add_argument_group("optimisation")
    opt.add_argument("--epochs", type=int, default=40, help="Number of epochs.")
    opt.add_argument("--batch-size", type=int, default=32, help="Batch size.")
    opt.add_argument("--lr", type=float, default=0.001, help="Learning rate.")

    misc = p.add_argument_group("misc")
    misc.add_argument("--seed", type=int, default=1, help="Random seed.")
    misc.add_argument("--device", default=None, help="cpu / cuda / auto (default: auto).")
    misc.add_argument("--output-dir", default="artifacts", help="Root artifact directory.")
    misc.add_argument(
        "--run-name",
        default=None,
        help="Name this run; output goes to <output-dir>/run_<name>/.",
    )
    misc.add_argument("--print-every", type=int, default=5, help="Print interval (epochs).")
    misc.add_argument("--plot-every", type=int, default=1, help="Loss-curve sample interval.")
    misc.add_argument("--n-samples", type=int, default=5, help="#sample translations to dump.")
    misc.add_argument(
        "--sample-sentences",
        nargs="*",
        default=[],
        help="Source sentences to render attention maps for.",
    )
    return p


def config_from_args(args: argparse.Namespace) -> TrainConfig:
    return TrainConfig(
        lang1=args.lang1,
        lang2=args.lang2,
        reverse=args.reverse,
        data_dir=args.data_dir,
        max_length=args.max_length,
        val_split=args.val_split,
        use_prefix_filter=args.prefix_filter,
        max_pairs=args.max_pairs,
        arch=args.arch,
        size=args.size,
        hidden_size=args.hidden_size,
        dropout=args.dropout,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
        device=args.device,
        output_dir=args.output_dir,
        run_name=args.run_name,
        print_every=args.print_every,
        plot_every=args.plot_every,
        n_samples=args.n_samples,
        sample_sentences=args.sample_sentences,
    )


def main() -> None:
    args = build_parser().parse_args()
    cfg = config_from_args(args)
    metrics = run_experiment(cfg)
    print(f"\nArtifacts written to: {metrics['run_dir']}")


if __name__ == "__main__":
    main()
