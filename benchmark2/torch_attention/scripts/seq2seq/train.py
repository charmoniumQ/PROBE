"""Training and evaluation routines (architecture-agnostic)."""
from __future__ import annotations

import math
import time
from collections import Counter
from typing import Callable, Dict, List, Optional, Tuple

import torch
import torch.nn as nn
from torch import optim
from torch.utils.data import DataLoader

from .data import EOS_token, Lang, tensor_from_sentence
from .utils import time_since


def train_epoch(
    dataloader: DataLoader,
    encoder: nn.Module,
    decoder: nn.Module,
    encoder_optimizer: optim.Optimizer,
    decoder_optimizer: optim.Optimizer,
    criterion: nn.Module,
) -> float:
    total_loss = 0.0
    for input_tensor, target_tensor in dataloader:
        encoder_optimizer.zero_grad()
        decoder_optimizer.zero_grad()

        encoder_outputs, encoder_hidden = encoder(input_tensor)
        decoder_outputs, _, _ = decoder(encoder_outputs, encoder_hidden, target_tensor)

        loss = criterion(
            decoder_outputs.view(-1, decoder_outputs.size(-1)),
            target_tensor.view(-1),
        )
        loss.backward()

        encoder_optimizer.step()
        decoder_optimizer.step()
        total_loss += loss.item()

    return total_loss / len(dataloader)


@torch.no_grad()
def evaluate_loss(
    dataloader: DataLoader,
    encoder: nn.Module,
    decoder: nn.Module,
    criterion: nn.Module,
) -> float:
    encoder.eval()
    decoder.eval()
    total_loss = 0.0
    for input_tensor, target_tensor in dataloader:
        encoder_outputs, encoder_hidden = encoder(input_tensor)
        decoder_outputs, _, _ = decoder(encoder_outputs, encoder_hidden, target_tensor)
        loss = criterion(
            decoder_outputs.view(-1, decoder_outputs.size(-1)),
            target_tensor.view(-1),
        )
        total_loss += loss.item()
    encoder.train()
    decoder.train()
    return total_loss / max(len(dataloader), 1)


@torch.no_grad()
def evaluate(
    encoder: nn.Module,
    decoder: nn.Module,
    sentence: str,
    input_lang: Lang,
    output_lang: Lang,
    device: torch.device,
) -> Tuple[List[str], Optional[torch.Tensor]]:
    """Greedy-decode a single sentence, returning words and attention."""
    encoder.eval()
    decoder.eval()
    input_tensor = tensor_from_sentence(input_lang, sentence, device)

    encoder_outputs, encoder_hidden = encoder(input_tensor)
    decoder_outputs, _, decoder_attn = decoder(encoder_outputs, encoder_hidden)

    _, topi = decoder_outputs.topk(1)
    decoded_ids = topi.squeeze()

    decoded_words: List[str] = []
    for idx in decoded_ids:
        token = idx.item()
        if token == EOS_token:
            decoded_words.append("<EOS>")
            break
        decoded_words.append(output_lang.index2word.get(token, "<UNK>"))
    return decoded_words, decoder_attn


@torch.no_grad()
def evaluate_accuracy(
    encoder: nn.Module,
    decoder: nn.Module,
    pairs,
    input_lang: Lang,
    output_lang: Lang,
    device: torch.device,
    limit: Optional[int] = 500,
) -> dict:
    """Return accuracy metrics on greedy decodes (word-acc, exact-match, BLEU, F1)."""
    sample = pairs[:limit] if limit else pairs
    total_words = 0
    correct_words = 0
    exact = 0
    predictions: List[List[str]] = []
    references: List[List[str]] = []

    for src, tgt in sample:
        pred_words, _ = evaluate(encoder, decoder, src, input_lang, output_lang, device)
        pred = [w for w in pred_words if w != "<EOS>"]
        gold = tgt.split(" ")
        predictions.append(pred)
        references.append(gold)
        for i, gold_word in enumerate(gold):
            total_words += 1
            if i < len(pred) and pred[i] == gold_word:
                correct_words += 1
        if pred == gold:
            exact += 1

    word_acc = correct_words / max(total_words, 1)
    exact_acc = exact / max(len(sample), 1)

    pred_tokens = sum(len(p) for p in predictions)
    ref_tokens = sum(len(r) for r in references)
    precision = correct_words / max(pred_tokens, 1)
    recall = correct_words / max(ref_tokens, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)

    bleu_metrics = _corpus_bleu(predictions, references)

    return {
        "word_accuracy": round(word_acc, 4),
        "exact_match": round(exact_acc, 4),
        "token_precision": round(precision, 4),
        "token_recall": round(recall, 4),
        "token_f1": round(f1, 4),
        **bleu_metrics,
    }


def _ngrams(tokens: List[str], n: int) -> Counter:
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def _corpus_bleu(
    predictions: List[List[str]],
    references: List[List[str]],
    max_n: int = 4,
) -> Dict[str, float]:
    """Compute corpus-level BLEU-1 through BLEU-4 (standard smoothed corpus BLEU)."""
    precisions: List[float] = []
    for n in range(1, max_n + 1):
        pred_counts: Counter = Counter()
        ref_counts: Counter = Counter()
        for pred, ref in zip(predictions, references):
            pred_counts += _ngrams(pred, n)
            ref_counts += _ngrams(ref, n)

        clipped_count = 0
        pred_total = sum(pred_counts.values())
        for ngram, count in pred_counts.items():
            clipped_count += min(count, ref_counts.get(ngram, 0))

        precisions.append(clipped_count / pred_total if pred_total > 0 else 0.0)

    ref_len = sum(len(r) for r in references)
    pred_len = sum(len(p) for p in predictions)
    if pred_len == 0:
        bp = 0.0
    elif pred_len >= ref_len:
        bp = 1.0
    else:
        bp = math.exp(1.0 - ref_len / pred_len)

    results: Dict[str, float] = {}
    for i in range(max_n):
        valid = [p for p in precisions[: i + 1] if p > 0]
        if not valid:
            results[f"bleu_{i + 1}"] = 0.0
        else:
            geom_mean = math.exp(sum(math.log(p) for p in valid) / (i + 1))
            results[f"bleu_{i + 1}"] = round(bp * geom_mean, 4)

    results["bleu"] = results.get(f"bleu_{max_n}", 0.0)
    return results


def train(
    train_loader: DataLoader,
    encoder: nn.Module,
    decoder: nn.Module,
    n_epochs: int,
    learning_rate: float = 0.001,
    val_loader: Optional[DataLoader] = None,
    print_every: int = 5,
    plot_every: int = 1,
    on_epoch: Optional[Callable[[int, float, Optional[float]], None]] = None,
) -> Tuple[List[float], List[float]]:
    """Train the model, returning per-``plot_every`` train and val loss curves."""
    start = time.time()
    plot_train_losses: List[float] = []
    plot_val_losses: List[float] = []
    print_loss_total = 0.0
    plot_loss_total = 0.0

    encoder_optimizer = optim.Adam(encoder.parameters(), lr=learning_rate)
    decoder_optimizer = optim.Adam(decoder.parameters(), lr=learning_rate)
    criterion = nn.NLLLoss()

    for epoch in range(1, n_epochs + 1):
        loss = train_epoch(
            train_loader, encoder, decoder, encoder_optimizer, decoder_optimizer, criterion
        )
        print_loss_total += loss
        plot_loss_total += loss

        val_loss = None
        if val_loader is not None and (epoch % plot_every == 0 or epoch == n_epochs):
            val_loss = evaluate_loss(val_loader, encoder, decoder, criterion)

        if on_epoch is not None:
            on_epoch(epoch, loss, val_loss)

        if print_every and epoch % print_every == 0:
            print_loss_avg = print_loss_total / print_every
            print_loss_total = 0.0
            val_str = f" val={val_loss:.4f}" if val_loss is not None else ""
            print(
                "%s (%d %d%%) train=%.4f%s"
                % (
                    time_since(start, epoch / n_epochs),
                    epoch,
                    epoch / n_epochs * 100,
                    print_loss_avg,
                    val_str,
                )
            )

        if plot_every and epoch % plot_every == 0:
            plot_train_losses.append(plot_loss_total / plot_every)
            plot_loss_total = 0.0
            if val_loss is not None:
                plot_val_losses.append(val_loss)

    return plot_train_losses, plot_val_losses
