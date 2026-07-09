"""Filesystem, JSON and timing helpers with no torch / numpy dependency."""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any


def ensure_dir(path: str) -> str:
    """Create ``path`` (and parents) if missing and return it."""
    os.makedirs(path, exist_ok=True)
    return path


def as_minutes(seconds: float) -> str:
    minutes = math.floor(seconds / 60)
    seconds -= minutes * 60
    return "%dm %ds" % (minutes, seconds)


def time_since(since: float, percent: float) -> str:
    now = time.time()
    elapsed = now - since
    estimated_total = elapsed / max(percent, 1e-9)
    remaining = estimated_total - elapsed
    return "%s (- %s)" % (as_minutes(elapsed), as_minutes(remaining))


def save_json(obj: Any, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
