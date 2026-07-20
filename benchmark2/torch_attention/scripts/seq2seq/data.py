"""Data loading, normalisation and vocabulary handling.

Generalised from the tutorial so that *any* ``lang1-lang2`` tab-separated
file placed under the data directory can be used, in either direction.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from io import open
from typing import List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader, RandomSampler, TensorDataset

# Pure-text helpers (vocabulary, normalisation, canonical alphabet) live in the
# torch-free :mod:`seq2seq.text` module and are re-exported here for backwards
# compatibility.
from .text import (
    CANONICAL_ALPHABET,
    ENG_PREFIXES,
    EOS_token,
    SOS_token,
    Lang,
    is_canonical,
    normalize_string,
    unicode_to_ascii,
)

Pair = List[str]


def read_langs(
    lang1: str,
    lang2: str,
    data_dir: str = "data",
    reverse: bool = False,
) -> Tuple[Lang, Lang, List[Pair]]:
    """Read ``<data_dir>/<lang1>-<lang2>.txt`` into normalised pairs."""
    print(f"Reading lines from {data_dir}/{lang1}-{lang2}.txt ...")
    path = f"{data_dir}/{lang1}-{lang2}.txt"
    lines = open(path, encoding="utf-8").read().strip().split("\n")

    pairs = [[normalize_string(s) for s in line.split("\t")[:2]] for line in lines]

    if reverse:
        pairs = [list(reversed(p)) for p in pairs]
        input_lang = Lang(lang2)
        output_lang = Lang(lang1)
    else:
        input_lang = Lang(lang1)
        output_lang = Lang(lang2)

    return input_lang, output_lang, pairs


def make_pair_filter(max_length: int, prefix_filter: Optional[Sequence[str]]):
    def filter_pair(pair: Pair) -> bool:
        if len(pair) < 2 or not pair[0] or not pair[1]:
            return False
        short_enough = (
            len(pair[0].split(" ")) < max_length
            and len(pair[1].split(" ")) < max_length
        )
        if not short_enough:
            return False
        if prefix_filter:
            return pair[1].startswith(tuple(prefix_filter))
        return True

    return filter_pair


def prepare_data(
    lang1: str,
    lang2: str,
    data_dir: str = "data",
    reverse: bool = False,
    max_length: int = 10,
    use_prefix_filter: bool = True,
    max_pairs: Optional[int] = None,
) -> Tuple[Lang, Lang, List[Pair]]:
    input_lang, output_lang, pairs = read_langs(lang1, lang2, data_dir, reverse)
    print("Read %s sentence pairs" % len(pairs))

    # The prefix filter is English-specific; only apply it when the *output*
    # language is English so it stays meaningful for arbitrary pairs.
    prefix_filter = None
    if use_prefix_filter and output_lang.name.lower().startswith("eng"):
        prefix_filter = ENG_PREFIXES
    pairs = [p for p in pairs if make_pair_filter(max_length, prefix_filter)(p)]
    print("Trimmed to %s sentence pairs" % len(pairs))

    if max_pairs is not None and len(pairs) > max_pairs:
        pairs = random.sample(pairs, max_pairs)
        print("Sub-sampled to %s sentence pairs" % len(pairs))

    print("Counting words...")
    for pair in pairs:
        input_lang.add_sentence(pair[0])
        output_lang.add_sentence(pair[1])
    print("Counted words:")
    print(" ", input_lang.name, input_lang.n_words)
    print(" ", output_lang.name, output_lang.n_words)
    return input_lang, output_lang, pairs


def indexes_from_sentence(lang: Lang, sentence: str) -> List[int]:
    return [lang.word2index[word] for word in sentence.split(" ") if word]


def tensor_from_sentence(lang: Lang, sentence: str, device: torch.device) -> torch.Tensor:
    indexes = indexes_from_sentence(lang, sentence)
    indexes.append(EOS_token)
    return torch.tensor(indexes, dtype=torch.long, device=device).view(1, -1)


def _pad_ids(pairs: Sequence[Pair], input_lang: Lang, output_lang: Lang, max_length: int):
    n = len(pairs)
    input_ids = np.zeros((n, max_length), dtype=np.int64)
    target_ids = np.zeros((n, max_length), dtype=np.int64)
    for idx, (inp, tgt) in enumerate(pairs):
        inp_ids = indexes_from_sentence(input_lang, inp)[: max_length - 1]
        tgt_ids = indexes_from_sentence(output_lang, tgt)[: max_length - 1]
        inp_ids.append(EOS_token)
        tgt_ids.append(EOS_token)
        input_ids[idx, : len(inp_ids)] = inp_ids
        target_ids[idx, : len(tgt_ids)] = tgt_ids
    return input_ids, target_ids


@dataclass
class DataBundle:
    input_lang: Lang
    output_lang: Lang
    train_pairs: List[Pair]
    val_pairs: List[Pair]
    train_loader: DataLoader
    val_loader: DataLoader
    max_length: int


def build_dataset(
    lang1: str,
    lang2: str,
    data_dir: str = "data",
    reverse: bool = False,
    max_length: int = 10,
    batch_size: int = 32,
    val_split: float = 0.1,
    use_prefix_filter: bool = True,
    max_pairs: Optional[int] = None,
    device: Optional[torch.device] = None,
) -> DataBundle:
    """Prepare vocabularies and train/val dataloaders for a language pair."""
    device = device or torch.device("cpu")
    input_lang, output_lang, pairs = prepare_data(
        lang1,
        lang2,
        data_dir=data_dir,
        reverse=reverse,
        max_length=max_length,
        use_prefix_filter=use_prefix_filter,
        max_pairs=max_pairs,
    )

    random.shuffle(pairs)
    n_val = int(len(pairs) * val_split)
    val_pairs = pairs[:n_val]
    train_pairs = pairs[n_val:] or pairs
    val_pairs = val_pairs or train_pairs[: max(1, len(train_pairs) // 10)]

    train_in, train_tgt = _pad_ids(train_pairs, input_lang, output_lang, max_length)
    val_in, val_tgt = _pad_ids(val_pairs, input_lang, output_lang, max_length)

    train_data = TensorDataset(
        torch.LongTensor(train_in).to(device), torch.LongTensor(train_tgt).to(device)
    )
    val_data = TensorDataset(
        torch.LongTensor(val_in).to(device), torch.LongTensor(val_tgt).to(device)
    )

    train_loader = DataLoader(
        train_data, sampler=RandomSampler(train_data), batch_size=batch_size
    )
    val_loader = DataLoader(val_data, batch_size=batch_size)

    return DataBundle(
        input_lang=input_lang,
        output_lang=output_lang,
        train_pairs=train_pairs,
        val_pairs=val_pairs,
        train_loader=train_loader,
        val_loader=val_loader,
        max_length=max_length,
    )
