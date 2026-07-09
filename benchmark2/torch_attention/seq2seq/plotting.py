"""Plotting helpers. Uses the non-interactive ``agg`` backend for headless runs."""
from __future__ import annotations

from typing import Mapping, Optional, Sequence

import matplotlib

matplotlib.use("agg")

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as ticker  # noqa: E402


def plot_losses(
    train_losses: Sequence[float],
    val_losses: Optional[Sequence[float]],
    path: str,
    title: str = "Training loss",
) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(range(1, len(train_losses) + 1), train_losses, label="train")
    if val_losses:
        ax.plot(range(1, len(val_losses) + 1), val_losses, label="val")
    ax.set_xlabel("checkpoint")
    ax.set_ylabel("NLL loss")
    ax.set_title(title)
    ax.legend()
    ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=8))
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_attention(
    input_sentence: str,
    output_words: Sequence[str],
    attentions,
    path: str,
) -> None:
    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111)
    cax = ax.matshow(attentions.cpu().numpy(), cmap="bone")
    fig.colorbar(cax)

    x_labels = [""] + input_sentence.split(" ") + ["<EOS>"]
    y_labels = [""] + list(output_words)
    ax.set_xticks(range(len(x_labels)))
    ax.set_yticks(range(len(y_labels)))
    ax.set_xticklabels(x_labels, rotation=90)
    ax.set_yticklabels(y_labels)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(1))
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_comparison_curves(
    curves: Mapping[str, Sequence[float]],
    path: str,
    ylabel: str = "val NLL loss",
    title: str = "Validation loss by architecture",
) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    for label, values in curves.items():
        if values:
            ax.plot(range(1, len(values) + 1), values, label=label)
    ax.set_xlabel("checkpoint")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_comparison_bars(
    labels: Sequence[str],
    values: Sequence[float],
    path: str,
    ylabel: str,
    title: str,
) -> None:
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 5))
    positions = range(len(labels))
    bars = ax.bar(positions, values, color="#4c72b0")
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    for bar, value in zip(bars, values):
        ax.annotate(
            f"{value:.3g}",
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_grouped_bars(
    group_labels: Sequence[str],
    series: Mapping[str, Sequence[float]],
    path: str,
    ylabel: str,
    title: str,
) -> None:
    """Grouped bar chart: one group per label, one bar per series."""
    fig, ax = plt.subplots(figsize=(max(6, len(group_labels) * 1.6), 5))
    n_series = max(len(series), 1)
    width = 0.8 / n_series
    for i, (name, values) in enumerate(series.items()):
        positions = [x + i * width for x in range(len(group_labels))]
        ax.bar(positions, values, width=width, label=name)
    ax.set_xticks([x + width * (n_series - 1) / 2 for x in range(len(group_labels))])
    ax.set_xticklabels(group_labels, rotation=30, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_length_histogram(
    series: Mapping[str, Sequence[int]],
    path: str,
    title: str = "Sentence length distribution",
    xlabel: str = "length (words)",
) -> None:
    """Overlaid histograms of sentence lengths per language."""
    fig, ax = plt.subplots(figsize=(8, 5))
    all_values = [v for values in series.values() for v in values]
    max_len = max(all_values) if all_values else 1
    bins = range(0, max_len + 2)
    for name, values in series.items():
        ax.hist(list(values), bins=bins, alpha=0.5, label=name)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("count")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
