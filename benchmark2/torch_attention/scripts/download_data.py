#!/usr/bin/env python
"""Download datasets for the seq2seq pipeline.

The archive is fetched and unpacked inside a temporary directory; only the
single tab-separated data file is copied to the output path. Nothing else
(``data.zip``, the ``names/`` corpus, or a nested ``data/`` directory) is left
behind in the working tree.

Tutorial bundle (English/French pairs)::

    python download_data.py                       # -> data/eng-fra.txt
    python download_data.py --output some/eng-fra.txt

Additional Tatoeba/Anki pairs from https://www.manythings.org/anki/ (these
arrive as ``<other>-eng.zip`` archives containing ``<other>.txt`` with three
tab-separated columns ``English<TAB>Other<TAB>attribution``)::

    python download_data.py --anki spa            # -> data/eng-spa.txt
    python download_data.py --anki deu --output data/eng-deu.txt

After downloading, run ``clean_data.py`` on each file to obtain the canonical
(pre-processed) form, and ``verify_datasets.py`` to confirm two cleaned files
are indistinguishable in format.
"""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import zipfile
from typing import Callable, List, Optional

import requests

TUTORIAL_URL = "https://download.pytorch.org/tutorial/data.zip"
ANKI_BASE = "https://www.manythings.org/anki"
# manythings.org rejects requests without a browser-like User-Agent.
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def _stream_download(url: str, dest: str, headers: Optional[dict] = None) -> None:
    with requests.get(url, stream=True, headers=headers, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def _select_member(namelist: List[str], basename: str) -> str:
    for name in namelist:
        if os.path.basename(name) == basename:
            return name
    raise SystemExit(f"'{basename}' not found in archive; members: {namelist}")


def download_zip_member(
    url: str,
    member_basename: str,
    output_path: str,
    headers: Optional[dict] = None,
) -> str:
    """Download a zip into a tempdir, extract one member, copy it to output.

    The temporary directory (and the downloaded archive) are removed on exit;
    only ``output_path`` remains.
    """
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="seq2seq_dl_") as tmp:
        zip_path = os.path.join(tmp, "download.zip")
        print(f"Downloading {url}")
        print(f"  (temp dir: {tmp})")
        _stream_download(url, zip_path, headers=headers)

        with zipfile.ZipFile(zip_path) as zf:
            member = _select_member(zf.namelist(), member_basename)
            extracted = zf.extract(member, tmp)

        shutil.copyfile(extracted, output_path)

    n_lines = sum(1 for _ in open(output_path, encoding="utf-8"))
    print(f"Wrote {output_path} ({n_lines} lines).")
    return output_path


def download_tutorial(output_path: str = "data/eng-fra.txt") -> str:
    """Fetch the tutorial bundle and output only the eng-fra pairs file."""
    return download_zip_member(TUTORIAL_URL, "eng-fra.txt", output_path)


def download_anki(other: str, output_path: Optional[str] = None) -> str:
    """Fetch the ``<other>-eng`` anki pair and output only the pairs file."""
    output_path = output_path or os.path.join("data", f"eng-{other}.txt")
    return download_zip_member(
        f"{ANKI_BASE}/{other}-eng.zip",
        f"{other}.txt",
        output_path,
        headers=BROWSER_HEADERS,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--anki",
        default=None,
        metavar="LANG",
        help="Download the <LANG>-eng anki pair (e.g. spa, deu) instead of the tutorial bundle.",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Destination path for the single data file (default derived from --data-dir).",
    )
    p.add_argument(
        "--data-dir",
        default="data",
        help="Used to derive the default --output location.",
    )
    p.add_argument(
        "--n-copies",
        type=int,
        default=20,
        help="Repeat the downloaded data N times in the output file.",
    )
    args = p.parse_args()

    if args.anki:
        output = args.output or os.path.join(args.data_dir, f"eng-{args.anki}.txt")
        download_anki(args.anki, output)
    else:
        output = args.output or os.path.join(args.data_dir, "eng-fra.txt")
        download_tutorial(output)

    if args.n_copies > 1:
        with open(output, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        with open(output, "w", encoding="utf-8") as fh:
            for _ in range(args.n_copies):
                fh.writelines(lines)
        n_lines = sum(1 for _ in open(output, encoding="utf-8"))
        print(f"Duplicated {len(lines)} lines x{args.n_copies}: wrote {n_lines} total lines.")


if __name__ == "__main__":
    main()
