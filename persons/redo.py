"""
Redo-mode candidate detection.

Compares each polished transcript's `processed_at_db_state` against current
voiceprint DB state. Files where either participant has gained sessions
≥ threshold become candidates. Also supports filtering by student/teacher,
confidence-below, after-date, and --all.

Redo reuses Phase 1, 3, 4, 5, 6, 7 cached outputs; only Phase 8 (identify),
Phase 9 (polish), Phase 10 (corpus update) re-run.
"""
from __future__ import annotations

from pathlib import Path


def current_db_snapshot() -> dict[str, dict]:
    """Return {person_id: {n_sessions, observed_regions}} from current registry."""
    raise NotImplementedError


def is_stale(
    stamped_state: dict,
    current_state: dict[str, dict],
    threshold: int,
) -> bool:
    """True if any participant has gained ≥threshold sessions since stamping."""
    raise NotImplementedError


def find_candidates(
    threshold: int,
    student: str | None = None,
    teacher: str | None = None,
    confidence_below: float | None = None,
    after: str | None = None,
    redo_all: bool = False,
) -> list[Path]:
    """Enumerate polished transcripts matching redo criteria."""
    raise NotImplementedError


def redo_one(polished_path: Path) -> None:
    """Re-run Phase 8-10 for a file, reusing cached Phase 1-7 artifacts."""
    raise NotImplementedError
