"""
Atomic write helpers.

Every pipeline output is written as:
  1. create `<path>.tmp`
  2. write+flush+fsync
  3. os.replace(`<path>.tmp`, `<path>`)

A crash between steps 1 and 3 leaves a `.tmp` with no rename — easy to
detect and purge. The final `<path>` is never observed in a half-written
state.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write `data` to `path` via tmp-file + os.replace."""
    raise NotImplementedError


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Text variant of atomic_write_bytes."""
    raise NotImplementedError


def atomic_write_json(path: Path, obj: Any, indent: int = 2) -> None:
    """Serialize obj to JSON and write atomically."""
    raise NotImplementedError


def purge_tmp_siblings(directory: Path) -> int:
    """Remove any orphaned `*.tmp` files under `directory`. Returns count removed."""
    raise NotImplementedError
