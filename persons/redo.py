"""
Redo-mode candidate detection.

Compares each polished transcript's `processed_at_db_state` against the
current voiceprint DB state. Files where either participant has gained
≥threshold sessions since stamping become candidates. Supports filtering
by student/teacher id, segment-level confidence floor, processed-before
date, and --all.

Redo reuses Phase 1, 3, 4, 5, 6, 7 cached outputs; only Phase 8
(identify), Phase 9 (polish), Phase 10 (corpus update) re-run.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from config import POLISHED_DIR
from persons.registry import list_all
from persons.schema import total_sessions

log = logging.getLogger(__name__)


def current_db_snapshot() -> dict[str, dict]:
    """Snapshot of {person_id: {n_sessions, observed_regions}} from the registry."""
    out: dict[str, dict] = {}
    for p in list_all():
        out[p.id] = {
            "n_sessions": total_sessions(p),
            "observed_regions": list(p.observed_regions),
        }
    return out


def _load_stamped(polished: Path) -> tuple[dict, dict]:
    """Return (processed_at_db_state, full_transcript)."""
    with open(polished, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return (data.get("processed_at_db_state") or {}, data)


def is_stale(
    stamped_state: dict,
    current_state: dict[str, dict],
    threshold: int,
) -> bool:
    """True iff any participant has gained ≥threshold sessions since stamping."""
    for person_id, stamped in stamped_state.items():
        current = current_state.get(person_id)
        if current is None:
            continue
        gained = current["n_sessions"] - int(stamped.get("n_sessions", 0))
        if gained >= threshold:
            return True
    return False


def find_candidates(
    threshold: int,
    student: str | None = None,
    teacher: str | None = None,
    confidence_below: float | None = None,
    after: str | None = None,
    redo_all: bool = False,
) -> list[Path]:
    """Enumerate polished transcripts matching the combined redo criteria."""
    if not POLISHED_DIR.exists():
        return []
    after_dt = _parse_iso(after) if after else None
    current = current_db_snapshot()
    hits: list[Path] = []

    for polished in sorted(POLISHED_DIR.glob("*.json")):
        try:
            stamped, transcript = _load_stamped(polished)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read %s: %s", polished, exc)
            continue

        if student and not _has_participant(transcript, student, "student"):
            continue
        if teacher and not _has_participant(transcript, teacher, "teacher"):
            continue
        if after_dt is not None:
            processed_at = _parse_iso(transcript.get("processed_at"))
            if processed_at is None or processed_at >= after_dt:
                continue
        if confidence_below is not None and not _has_low_confidence(
            transcript, confidence_below
        ):
            continue
        if redo_all or is_stale(stamped, current, threshold):
            hits.append(polished)

    return hits


def _has_participant(transcript: dict, person_id: str, role: str) -> bool:
    for p in transcript.get("participants") or []:
        if p.get("id") == person_id and p.get("role") == role:
            return True
    return False


def _has_low_confidence(transcript: dict, floor: float) -> bool:
    for seg in transcript.get("segments") or []:
        conf = seg.get("speaker_confidence")
        if conf is not None and conf < floor:
            return True
    return False


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None
