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
import os
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write `data` to `path` via tmp-file + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Text variant of atomic_write_bytes."""
    atomic_write_bytes(Path(path), text.encode(encoding))


def atomic_write_json(path: Path, obj: Any, indent: int = 2) -> None:
    """Serialize obj to JSON and write atomically."""
    atomic_write_text(path, json.dumps(obj, indent=indent, ensure_ascii=False))


def purge_tmp_siblings(directory: Path) -> int:
    """Remove any orphaned `*.tmp` files under `directory`. Returns count removed."""
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    count = 0
    for tmp in directory.glob("*.tmp"):
        try:
            tmp.unlink()
            count += 1
        except OSError:
            pass
    return count
