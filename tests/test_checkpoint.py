"""Unit tests for core.file_hasher."""

import os
import sys
import time
from pathlib import Path

# Make backend/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.file_hasher import compute_sidecar_hash, sidecar_matches


def test_hash_stable_for_unchanged_file(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"x" * 200_000)
    a = compute_sidecar_hash(f)
    b = compute_sidecar_hash(f)
    assert a == b
    assert a is not None
    assert len(a) == 64


def test_hash_changes_on_content_edit(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"x" * 200_000)
    a = compute_sidecar_hash(f)
    # Modify the tail; head+size stay the same but tail chunk differs
    with f.open("r+b") as fh:
        fh.seek(-10, os.SEEK_END)
        fh.write(b"mutated!!!")
    # Force mtime tick on fast filesystems
    now = time.time()
    os.utime(f, (now, now + 1))
    b = compute_sidecar_hash(f)
    assert a != b


def test_hash_changes_on_size_change(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"x" * 1000)
    a = compute_sidecar_hash(f)
    f.write_bytes(b"x" * 2000)
    now = time.time()
    os.utime(f, (now, now + 1))
    b = compute_sidecar_hash(f)
    assert a != b


def test_hash_none_for_missing_file(tmp_path):
    assert compute_sidecar_hash(tmp_path / "nope.bin") is None


def test_sidecar_matches_legacy_missing_hash(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"x" * 100)
    # stored_hash None/empty => legacy sidecar, always matches
    assert sidecar_matches(f, None) is True
    assert sidecar_matches(f, "") is True


def test_sidecar_matches_equal_hash(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"y" * 100)
    h = compute_sidecar_hash(f)
    assert sidecar_matches(f, h) is True


def test_sidecar_matches_wrong_hash(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"y" * 100)
    assert sidecar_matches(f, "0" * 64) is False


def test_sidecar_matches_file_replaced(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"original" * 20)
    h = compute_sidecar_hash(f)
    # Replace with different content
    f.write_bytes(b"different" * 30)
    now = time.time()
    os.utime(f, (now, now + 1))
    assert sidecar_matches(f, h) is False
