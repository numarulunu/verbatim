"""
Remove intermediate files after final outputs are verified.

Only deletes entries under 01_acapella/ and 02_raw_json/ whose corresponding
03_polished/<file_id>.json exists AND validates against the output schema.
Never touches _voiceprints/, corpus.json, session_map.json, Material/.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def find_safe_to_delete() -> list[Path]:
    """Return intermediate files where a valid polished counterpart exists."""
    raise NotImplementedError


def verify_polished(polished_path: Path) -> bool:
    """Schema-validate a polished JSON. Returns True if safe to clean upstream."""
    raise NotImplementedError


def delete(paths: list[Path], dry_run: bool = False) -> None:
    """Remove given paths; in dry_run, only log."""
    raise NotImplementedError


def build_arg_parser() -> argparse.ArgumentParser:
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
