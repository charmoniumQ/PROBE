"""Sequence-to-sequence translation toolkit.

A small, modular re-implementation of the PyTorch seq2seq translation
tutorial that supports:

* Multiple language pairs (any ``lang1-lang2`` file under ``data/``).
* Multiple model architectures (see :mod:`seq2seq.models`).
* Configurable hyperparameters.
* Artifact emission (loss curves, attention maps, metrics, checkpoints).

The heavy (torch-backed) names below are imported lazily via module-level
``__getattr__`` (PEP 562). This means torch-free submodules such as
:mod:`seq2seq.text` and :mod:`seq2seq.io_utils` can be imported without
dragging in the tensor stack -- which is what lets ``clean_data.py`` and
``verify_datasets.py`` run without torch installed.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

# name -> submodule that defines it (imported on first access only).
_LAZY = {
    "SOS_token": ".text",
    "EOS_token": ".text",
    "Lang": ".text",
    "build_dataset": ".data",
    "ARCHITECTURES": ".models",
    "build_model": ".models",
    "TrainConfig": ".experiment",
    "run_experiment": ".experiment",
    "LoadedModel": ".experiment",
    "load_checkpoint": ".experiment",
}

__all__ = list(_LAZY)


def __getattr__(name: str):
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module, __name__), name)


def __dir__():
    return sorted(list(globals().keys()) + __all__)


if TYPE_CHECKING:  # pragma: no cover - for type checkers / IDEs only
    from .data import build_dataset
    from .experiment import LoadedModel, TrainConfig, load_checkpoint, run_experiment
    from .models import ARCHITECTURES, build_model
    from .text import EOS_token, SOS_token, Lang
