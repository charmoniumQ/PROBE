"""Shared utilities: device selection, seeding and parameter counting.

Torch-free filesystem / JSON / timing helpers live in :mod:`seq2seq.io_utils`
and are re-exported here for convenience.
"""
from __future__ import annotations

import random

import numpy as np
import torch

# Re-export the torch-free helpers so existing ``from seq2seq.utils import ...``
# call sites keep working.
from .io_utils import as_minutes, ensure_dir, load_json, save_json, time_since

__all__ = [
    "resolve_device",
    "set_seed",
    "count_parameters",
    "ensure_dir",
    "as_minutes",
    "time_since",
    "save_json",
    "load_json",
]


def resolve_device(device: str | None = None) -> torch.device:
    """Return a :class:`torch.device`, honouring an explicit override."""
    if device and device != "auto":
        return torch.device(device)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def set_seed(seed: int) -> None:
    """Seed python, numpy and torch RNGs for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def count_parameters(*modules: torch.nn.Module) -> int:
    """Count trainable parameters across one or more modules."""
    return sum(
        p.numel() for module in modules for p in module.parameters() if p.requires_grad
    )

