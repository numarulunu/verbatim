"""
Engine lock: at most one daemon may own the per-user voiceprint dir at
a time. The lock is a small JSON file written to
`_voiceprints/.engine.lock`. A second daemon startup either:
- rejects cleanly if the existing lock's PID is still alive;
- reclaims the lock if the existing PID is dead (crash recovery).

The lock is released on daemon exit (normal, ctrl-C, or top-level
exception — the lock is NOT released on OS crash, hence the stale-PID
reclaim path).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    monkeypatch.setenv("VERBATIM_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "config" or mod.startswith("persons."):
            sys.modules.pop(mod, None)
    # engine_lock may have cached config — reload too.
    sys.modules.pop("utils.engine_lock", None)
    yield tmp_path


def test_acquire_creates_lock_file_with_pid(tmp_project):
    import config
    from utils.engine_lock import acquire, release

    handle = acquire()
    try:
        lock_path = config.VOICEPRINT_DIR / ".engine.lock"
        assert lock_path.exists(), "lock file must be created on acquire"
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()
        assert "started_at" in payload
        assert "engine_version" in payload
    finally:
        release(handle)


def test_release_removes_lock_file(tmp_project):
    import config
    from utils.engine_lock import acquire, release

    handle = acquire()
    lock_path = config.VOICEPRINT_DIR / ".engine.lock"
    assert lock_path.exists()

    release(handle)
    assert not lock_path.exists(), "lock file must be removed on release"


def test_double_acquire_same_process_raises(tmp_project):
    from utils.engine_lock import EngineLockHeld, acquire, release

    h1 = acquire()
    try:
        with pytest.raises(EngineLockHeld) as excinfo:
            acquire()
        # Diagnostic message should name the holding PID so the Electron
        # wrapper can surface it to the user.
        assert str(os.getpid()) in str(excinfo.value)
    finally:
        release(h1)


def test_stale_lock_is_reclaimed_when_pid_is_dead(tmp_project, monkeypatch):
    """A lock written by a PID that no longer exists is silently reclaimed.
    Simulated by writing a lock file pointing at a PID that the module's
    psutil shim reports as dead."""
    import config
    from utils import engine_lock

    # Pre-seed a stale lock pointing at a PID we'll tell engine_lock is dead.
    stale_pid = 999_999
    config.VOICEPRINT_DIR.mkdir(parents=True, exist_ok=True)
    (config.VOICEPRINT_DIR / ".engine.lock").write_text(json.dumps({
        "pid": stale_pid,
        "started_at": "2000-01-01T00:00:00+00:00",
        "engine_version": "0.0.0",
    }), encoding="utf-8")

    monkeypatch.setattr(engine_lock, "_pid_alive", lambda pid: pid != stale_pid)

    handle = engine_lock.acquire()
    try:
        payload = json.loads(
            (config.VOICEPRINT_DIR / ".engine.lock").read_text(encoding="utf-8")
        )
        assert payload["pid"] == os.getpid(), "stale lock must be overwritten"
    finally:
        engine_lock.release(handle)


def test_live_lock_from_another_pid_rejects_acquire(tmp_project, monkeypatch):
    """A lock written by a LIVE foreign PID blocks the second daemon."""
    import config
    from utils import engine_lock

    other_pid = 12345  # pretend this is alive
    config.VOICEPRINT_DIR.mkdir(parents=True, exist_ok=True)
    (config.VOICEPRINT_DIR / ".engine.lock").write_text(json.dumps({
        "pid": other_pid,
        "started_at": "2025-01-01T00:00:00+00:00",
        "engine_version": "1.0.0",
    }), encoding="utf-8")

    monkeypatch.setattr(engine_lock, "_pid_alive", lambda pid: pid == other_pid)

    with pytest.raises(engine_lock.EngineLockHeld) as excinfo:
        engine_lock.acquire()
    assert str(other_pid) in str(excinfo.value)


def test_release_is_idempotent(tmp_project):
    from utils.engine_lock import acquire, release

    handle = acquire()
    release(handle)
    release(handle)  # must not raise


def test_release_does_not_delete_foreign_lock(tmp_project):
    """If the lock gets overwritten by someone else between acquire and
    release, release() must NOT delete the foreign lock. The handle
    remembers the content it wrote."""
    import config
    from utils.engine_lock import acquire, release

    handle = acquire()
    # Overwrite with a foreign lock.
    (config.VOICEPRINT_DIR / ".engine.lock").write_text(json.dumps({
        "pid": 424242,
        "started_at": "2025-12-31T00:00:00+00:00",
        "engine_version": "9.9.9",
    }), encoding="utf-8")

    release(handle)

    # Foreign lock must still exist.
    assert (config.VOICEPRINT_DIR / ".engine.lock").exists()
    payload = json.loads(
        (config.VOICEPRINT_DIR / ".engine.lock").read_text(encoding="utf-8")
    )
    assert payload["pid"] == 424242


def test_acquire_creates_parent_directory(tmp_project):
    """First daemon run may predate any voiceprint directory. acquire()
    must create `_voiceprints/` rather than fail."""
    import config
    from utils.engine_lock import acquire, release

    # Make sure the directory doesn't exist yet.
    if config.VOICEPRINT_DIR.exists():
        for p in config.VOICEPRINT_DIR.rglob("*"):
            if p.is_file():
                p.unlink()
        config.VOICEPRINT_DIR.rmdir()
    assert not config.VOICEPRINT_DIR.exists()

    handle = acquire()
    try:
        assert config.VOICEPRINT_DIR.exists()
        assert (config.VOICEPRINT_DIR / ".engine.lock").exists()
    finally:
        release(handle)


def test_corrupt_lock_file_is_treated_as_stale(tmp_project):
    """If the lock file is unreadable JSON, acquire() treats it as stale
    rather than refusing — prior session crashed during write."""
    import config
    from utils.engine_lock import acquire, release

    config.VOICEPRINT_DIR.mkdir(parents=True, exist_ok=True)
    (config.VOICEPRINT_DIR / ".engine.lock").write_text(
        "this is not json", encoding="utf-8"
    )

    handle = acquire()
    try:
        payload = json.loads(
            (config.VOICEPRINT_DIR / ".engine.lock").read_text(encoding="utf-8")
        )
        assert payload["pid"] == os.getpid()
    finally:
        release(handle)
