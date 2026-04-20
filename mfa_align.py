"""
Optional Montreal Forced Aligner phoneme alignment.

NOT part of the main pipeline. Separate Conda env. On-demand only.
Validates its own output: if <95% word overlap with transcript, MFA result
is rejected and the original wav2vec2 word timings are retained.

Writes `words_mfa` into existing polished JSON; leaves `words_wav2vec2`
untouched.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def align_one(file_id: str) -> bool:
    """Align a single polished transcript. Returns True on success."""
    raise NotImplementedError


def align_many(ids_or_glob: list[str]) -> None:
    """Batch-align multiple files or a glob pattern."""
    raise NotImplementedError


def verify(polished_path: Path) -> float:
    """Compute word-overlap ratio between MFA output and existing transcript."""
    raise NotImplementedError


def build_arg_parser() -> argparse.ArgumentParser:
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
