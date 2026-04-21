"""
Engine lock — coordinates single-daemon access to `_voiceprints/`.

The voiceprint registry is not safe for concurrent writers (registry
files + corpus.json are read-modify-write). A small JSON lock file at
`_voiceprints/.engine.lock` records the owning PID + start time. A second
daemon that starts while the lock is held either:
- fails fast with `EngineLockHeld` if the holding PID is still alive;
- reclaims silently if the PID is dead (crash recovery).

The lock is released on daemon exit. It is NOT flock-based, so an OS-
level crash leaves a stale file — the stale-PID reclaim path handles
that case.

Corrupt / unreadable lock files are treated as stale (a partial write
from a previous crash beats refusing to start).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)


class EngineLockHeld(RuntimeError):
    """Another daemon process holds the engine lock."""


class _LockHandle(NamedTuple):
    path: Path
    payload_text: str  # exact text we wrote, used by release() to avoid
                       # deleting a foreign lock that overwrote ours.


def _pid_alive(pid: int) -> bool:
    """Is the given PID currently alive?

    Uses psutil if available (handles PID recycling via create_time check
    indirectly — pid_exists is good enough for our purposes). Falls back
    to `os.kill(pid, 0)` on systems without psutil.
    """
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        # On Windows, PermissionError wraps ERROR_ACCESS_DENIED when the
        # process exists but can't be signalled — treat as alive.
        return True


def _lock_path() -> Path:
    from config import VOICEPRINT_DIR
    return Path(VOICEPRINT_DIR) / ".engine.lock"


def _read_existing(path: Path) -> dict | None:
    """Return the parsed lock file, or None if missing / unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def acquire(engine_version: str = "1.0.0") -> _LockHandle:
    """
    Take ownership of the engine lock. Raises `EngineLockHeld` if another
    live process already owns it. Silently reclaims stale / corrupt locks.
    """
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_existing(path)
    if existing is not None:
        other_pid = existing.get("pid")
        if isinstance(other_pid, int) and _pid_alive(other_pid):
            raise EngineLockHeld(
                f"engine lock held by pid {other_pid} "
                f"(started {existing.get('started_at')!r}, "
                f"engine_version={existing.get('engine_version')!r})"
            )
        log.info(
            "engine_lock: reclaiming stale lock from pid %r (dead or corrupt)",
            other_pid,
        )

    payload = {
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine_version": engine_version,
    }
    payload_text = json.dumps(payload, indent=2)
    path.write_text(payload_text, encoding="utf-8")
    log.info("engine_lock: acquired by pid %d", os.getpid())
    return _LockHandle(path=path, payload_text=payload_text)


def release(handle: _LockHandle) -> None:
    """
    Remove the lock file, but only if its content still matches what
    `acquire()` wrote. If someone else overwrote it, leave it alone —
    they now own the lock.

    Idempotent: a second call on the same handle is a no-op.
    """
    try:
        current = handle.path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except OSError as exc:
        log.warning("engine_lock: release read failed: %s", exc)
        return

    if current != handle.payload_text:
        log.warning(
            "engine_lock: release skipped — lock was overwritten by another process"
        )
        return

    try:
        handle.path.unlink()
        log.info("engine_lock: released by pid %d", os.getpid())
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("engine_lock: release unlink failed: %s", exc)
