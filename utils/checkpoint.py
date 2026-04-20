"""
Resume / staleness detection for the pipeline.

A stage's output is "fresh" iff its sidecar contains mtime, size, and sha256
matching the current source. Any mismatch invalidates downstream artifacts.

Carries forward the working logic from backend/core/file_hasher.py (SHA-256
over file contents) — kept as a distinct module because checkpoint semantics
extend beyond hashing (mtime + size cheap-checks first, hash only on tie).
"""
from __future__ import annotations

from pathlib import Path


def sha256_file(path: Path) -> str:
    """Streamed SHA-256 of a file (chunked to keep memory flat)."""
    raise NotImplementedError


def source_fingerprint(path: Path) -> dict:
    """Return {'mtime': ..., 'size': ..., 'sha256': ...} used by sidecars."""
    raise NotImplementedError


def is_fresh(source: Path, sidecar: dict) -> bool:
    """Compare current source fingerprint to sidecar's recorded values."""
    raise NotImplementedError


def sidecar_path_for(source: Path, stage: str) -> Path:
    """Return RAW_JSON_DIR/<stem>.<stage>.json path."""
    raise NotImplementedError
