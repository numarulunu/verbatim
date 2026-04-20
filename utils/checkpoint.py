"""
Resume / staleness detection for the pipeline.

A stage's output is "fresh" iff its sidecar's recorded source fingerprint
matches the current source. Cheap check (mtime + size) runs first; the
expensive SHA-256 is only consulted when cheap-check passes — so unchanged
files never re-hash.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from config import RAW_JSON_DIR

_HASH_CHUNK = 1 << 20  # 1 MiB


def sha256_file(path: Path) -> str:
    """Streamed SHA-256 of a file (chunked to keep memory flat)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def source_fingerprint(path: Path) -> dict:
    """Return {'mtime': int, 'size': int, 'sha256': hex} used in sidecars."""
    path = Path(path)
    stat = path.stat()
    return {
        "mtime": int(stat.st_mtime),
        "size": int(stat.st_size),
        "sha256": sha256_file(path),
    }


def is_fresh(source: Path, sidecar: dict) -> bool:
    """Compare current source fingerprint to sidecar's recorded values."""
    source = Path(source)
    if not source.exists() or not sidecar:
        return False
    stat = source.stat()
    if int(stat.st_mtime) != sidecar.get("mtime"):
        return False
    if int(stat.st_size) != sidecar.get("size"):
        return False
    expected = sidecar.get("sha256")
    if not expected:
        return True
    return sha256_file(source) == expected


def sidecar_path_for(source: Path, stage: str) -> Path:
    """Return RAW_JSON_DIR/<stem>.<stage>.json path."""
    stem = Path(source).stem
    return RAW_JSON_DIR / f"{stem}.{stage}.json"
