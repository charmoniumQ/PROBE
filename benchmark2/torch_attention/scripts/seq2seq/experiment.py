"""High-level experiment runner shared by the CLI scripts.

``run_experiment`` prepares data, builds a model, trains it, evaluates it and
writes all artifacts (loss curve, attention maps, sample translations, metrics
JSON and a checkpoint) into a per-run directory.
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional

import torch

from . import plotting
from .data import Lang, build_dataset
from .models import build_model, resolve_hidden_size
from .train import evaluate, evaluate_accuracy, train
from .utils import count_parameters, ensure_dir, resolve_device, save_json, set_seed


@dataclass
class TrainConfig:
    # Data / task
    lang1: str = "eng"
    lang2: str = "fra"
    reverse: bool = True
    data_dir: str = "data"
    max_length: int = 10
    val_split: float = 0.1
    use_prefix_filter: bool = True
    max_pairs: Optional[int] = None

    # Model
    arch: str = "bahdanau"
    size: Optional[str] = None
    hidden_size: Optional[int] = None
    dropout: float = 0.1

    # Optimisation
    epochs: int = 40
    batch_size: int = 32
    lr: float = 0.001

    # Misc
    seed: int = 1
    device: Optional[str] = None
    output_dir: str = "artifacts"
    run_name: Optional[str] = None
    print_every: int = 5
    plot_every: int = 1
    n_samples: int = 5
    sample_sentences: List[str] = field(default_factory=list)
    acc_limit: int = 500


def run_experiment(cfg: TrainConfig, verbose: bool = True) -> dict:
    """Run a single training experiment and emit artifacts.

    Returns a metrics dictionary (also written to ``metrics.json``).
    """
    set_seed(cfg.seed)
    device = resolve_device(cfg.device)
    hidden_size = resolve_hidden_size(cfg.size, cfg.hidden_size)
    if cfg.run_name:
        run_name = f"run_{cfg.run_name}"
    else:
        size_tag = cfg.size or f"h{hidden_size}"
        direction = f"{cfg.lang1}-{cfg.lang2}" + ("-rev" if cfg.reverse else "")
        run_name = f"{direction}_{cfg.arch}_{size_tag}"
    run_dir = ensure_dir(os.path.join(cfg.output_dir, run_name))

    if verbose:
        print(f"\n=== Run: {run_name} (device={device}, hidden={hidden_size}) ===")

    bundle = build_dataset(
        lang1=cfg.lang1,
        lang2=cfg.lang2,
        data_dir=cfg.data_dir,
        reverse=cfg.reverse,
        max_length=cfg.max_length,
        batch_size=cfg.batch_size,
        val_split=cfg.val_split,
        use_prefix_filter=cfg.use_prefix_filter,
        max_pairs=cfg.max_pairs,
        device=device,
    )

    encoder, decoder = build_model(
        arch=cfg.arch,
        input_size=bundle.input_lang.n_words,
        output_size=bundle.output_lang.n_words,
        hidden_size=hidden_size,
        max_length=cfg.max_length,
        device=device,
        dropout_p=cfg.dropout,
    )
    n_params = count_parameters(encoder, decoder)

    start = time.time()
    train_losses, val_losses = train(
        bundle.train_loader,
        encoder,
        decoder,
        n_epochs=cfg.epochs,
        learning_rate=cfg.lr,
        val_loader=bundle.val_loader,
        print_every=cfg.print_every if verbose else 0,
        plot_every=cfg.plot_every,
    )
    train_time = time.time() - start

    word_acc, exact_acc = evaluate_accuracy(
        encoder,
        decoder,
        bundle.val_pairs,
        bundle.input_lang,
        bundle.output_lang,
        device,
        limit=cfg.acc_limit,
    )

    # --- Artifacts -------------------------------------------------------
    plotting.plot_losses(
        train_losses,
        val_losses,
        os.path.join(run_dir, "loss_curve.png"),
        title=f"{run_name} loss",
    )

    sample_lines = _write_samples(cfg, bundle, encoder, decoder, device, run_dir)
    attn_files = _write_attention_maps(cfg, bundle, encoder, decoder, device, run_dir)

    torch.save(
        {
            "encoder": encoder.state_dict(),
            "decoder": decoder.state_dict(),
            "input_lang": bundle.input_lang.__dict__,
            "output_lang": bundle.output_lang.__dict__,
            "config": asdict(cfg),
            "hidden_size": hidden_size,
        },
        os.path.join(run_dir, "model.pt"),
    )

    metrics = {
        "run_name": run_name,
        "arch": cfg.arch,
        "size": cfg.size,
        "hidden_size": hidden_size,
        "lang1": cfg.lang1,
        "lang2": cfg.lang2,
        "reverse": cfg.reverse,
        "epochs": cfg.epochs,
        "batch_size": cfg.batch_size,
        "lr": cfg.lr,
        "n_params": n_params,
        "n_train_pairs": len(bundle.train_pairs),
        "n_val_pairs": len(bundle.val_pairs),
        "input_vocab": bundle.input_lang.n_words,
        "output_vocab": bundle.output_lang.n_words,
        "train_time_sec": round(train_time, 2),
        "final_train_loss": round(train_losses[-1], 4) if train_losses else None,
        "final_val_loss": round(val_losses[-1], 4) if val_losses else None,
        "word_accuracy": round(word_acc, 4),
        "exact_match": round(exact_acc, 4),
        "train_loss_curve": [round(x, 4) for x in train_losses],
        "val_loss_curve": [round(x, 4) for x in val_losses],
        "attention_maps": attn_files,
        "run_dir": run_dir,
    }
    save_json(metrics, os.path.join(run_dir, "metrics.json"))

    with open(os.path.join(run_dir, "samples.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(sample_lines))

    if verbose:
        print(
            f"--- {run_name}: val_loss={metrics['final_val_loss']} "
            f"word_acc={word_acc:.3f} exact={exact_acc:.3f} "
            f"params={n_params} time={train_time:.1f}s"
        )
    return metrics


def _write_samples(cfg, bundle, encoder, decoder, device, run_dir) -> List[str]:
    lines: List[str] = []
    pool = bundle.val_pairs or bundle.train_pairs
    n = min(cfg.n_samples, len(pool))
    for pair in random.sample(pool, n) if pool else []:
        words, _ = evaluate(
            encoder, decoder, pair[0], bundle.input_lang, bundle.output_lang, device
        )
        lines.append(f"> {pair[0]}")
        lines.append(f"= {pair[1]}")
        lines.append(f"< {' '.join(words)}")
        lines.append("")
    return lines


def _write_attention_maps(cfg, bundle, encoder, decoder, device, run_dir) -> List[str]:
    """Emit attention heatmaps (only meaningful for attention architectures)."""
    sentences = list(cfg.sample_sentences)
    if not sentences:
        pool = bundle.val_pairs or bundle.train_pairs
        n = min(4, len(pool))
        sentences = [p[0] for p in random.sample(pool, n)] if pool else []

    files: List[str] = []
    for i, sentence in enumerate(sentences):
        try:
            words, attentions = evaluate(
                encoder, decoder, sentence, bundle.input_lang, bundle.output_lang, device
            )
        except KeyError:
            # Sentence contains an out-of-vocabulary word; skip.
            continue
        if attentions is None:
            break  # architecture has no attention
        path = os.path.join(run_dir, f"attention_{i}.png")
        plotting.plot_attention(
            sentence, words, attentions[0, : len(words), :], path
        )
        files.append(os.path.basename(path))
    return files


@dataclass
class LoadedModel:
    encoder: "torch.nn.Module"
    decoder: "torch.nn.Module"
    input_lang: Lang
    output_lang: Lang
    config: TrainConfig
    hidden_size: int
    device: "torch.device"


def load_checkpoint(path: str, device: Optional[str] = None) -> LoadedModel:
    """Load a ``model.pt`` checkpoint and rebuild an eval-ready model."""
    dev = resolve_device(device)
    try:
        ckpt = torch.load(path, map_location=dev, weights_only=False)
    except TypeError:  # older torch without weights_only kwarg
        ckpt = torch.load(path, map_location=dev)

    input_lang = Lang.from_state(ckpt["input_lang"])
    output_lang = Lang.from_state(ckpt["output_lang"])
    cfg = TrainConfig(**ckpt["config"])
    hidden_size = ckpt["hidden_size"]

    encoder, decoder = build_model(
        arch=cfg.arch,
        input_size=input_lang.n_words,
        output_size=output_lang.n_words,
        hidden_size=hidden_size,
        max_length=cfg.max_length,
        device=dev,
        dropout_p=cfg.dropout,
    )
    encoder.load_state_dict(ckpt["encoder"])
    decoder.load_state_dict(ckpt["decoder"])
    encoder.eval()
    decoder.eval()

    return LoadedModel(
        encoder=encoder,
        decoder=decoder,
        input_lang=input_lang,
        output_lang=output_lang,
        config=cfg,
        hidden_size=hidden_size,
        device=dev,
    )
