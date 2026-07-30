"""Pure-text helpers: vocabulary, normalisation and the canonical alphabet.

This module deliberately imports **no torch / numpy**, so tools that only need
text preprocessing (``clean_data.py``, ``verify_datasets.py``) can import it
without pulling in the heavy tensor stack.
"""
from __future__ import annotations

import re
import unicodedata

SOS_token = 0
EOS_token = 1

# English "prefix" filter from the tutorial. Keeping the dataset tiny makes
# training fast enough to compare several architectures. Only applied when one
# side of the pair is English (or when explicitly requested).
ENG_PREFIXES = (
    "i am ", "i m ",
    "he is", "he s ",
    "she is", "she s ",
    "you are", "you re ",
    "we are", "we re ",
    "they are", "they re ",
)


class Lang:
    """Maps words to indices (and back) for a single language."""

    def __init__(self, name: str):
        self.name = name
        self.word2index: dict[str, int] = {}
        self.word2count: dict[str, int] = {}
        self.index2word: dict[int, str] = {SOS_token: "SOS", EOS_token: "EOS"}
        self.n_words = 2  # SOS and EOS

    def add_sentence(self, sentence: str) -> None:
        for word in sentence.split(" "):
            self.add_word(word)

    def add_word(self, word: str) -> None:
        if word not in self.word2index:
            self.word2index[word] = self.n_words
            self.word2count[word] = 1
            self.index2word[self.n_words] = word
            self.n_words += 1
        else:
            self.word2count[word] += 1

    @classmethod
    def from_state(cls, state: dict) -> "Lang":
        """Rebuild a :class:`Lang` from a saved ``__dict__`` state."""
        lang = cls(state["name"])
        lang.word2index = dict(state["word2index"])
        lang.word2count = dict(state["word2count"])
        lang.index2word = {int(k): v for k, v in state["index2word"].items()}
        lang.n_words = state["n_words"]
        return lang


def unicode_to_ascii(s: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_string(s: str) -> str:
    """Lowercase, trim and strip non-letter characters."""
    s = unicode_to_ascii(s.lower().strip())
    s = re.sub(r"([.!?])", r" \1", s)
    s = re.sub(r"[^a-zA-Z!?]+", r" ", s)
    return s.strip()


# The exact surface alphabet produced by :func:`normalize_string`: lowercase
# ASCII letters, single spaces, and the ``!`` / ``?`` tokens. Any preprocessed
# dataset must draw only from this set, which is what makes datasets from
# different languages *format-indistinguishable* after cleaning.
CANONICAL_ALPHABET = frozenset("abcdefghijklmnopqrstuvwxyz !?")


def is_canonical(text: str) -> bool:
    """True if ``text`` is exactly a :func:`normalize_string` output."""
    return (
        bool(text)
        and set(text) <= CANONICAL_ALPHABET
        and text == text.strip()
        and "  " not in text
    )
