"""Training and evaluation routines (architecture-agnostic)."""
from __future__ import annotations

import time
from typing import Callable, List, Optional, Tuple

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
) -> Tuple[float, float]:
    """Return (word-level accuracy, exact-match accuracy) on greedy decodes."""
    sample = pairs[:limit] if limit else pairs
    total_words = 0
    correct_words = 0
    exact = 0
    for src, tgt in sample:
        pred_words, _ = evaluate(encoder, decoder, src, input_lang, output_lang, device)
        pred = [w for w in pred_words if w != "<EOS>"]
        gold = tgt.split(" ")
        for i, gold_word in enumerate(gold):
            total_words += 1
            if i < len(pred) and pred[i] == gold_word:
                correct_words += 1
        if pred == gold:
            exact += 1
    word_acc = correct_words / max(total_words, 1)
    exact_acc = exact / max(len(sample), 1)
    return word_acc, exact_acc


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
