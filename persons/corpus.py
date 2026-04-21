"""
Corpus index — corpus.json.

One entry per processed session. Appended at the end of Phase 10. Replaced
(not duplicated) when a file is redone.
"""
from __future__ import annotations

import json
import logging

from config import CORPUS_FILE, POLISHED_DIR
from utils.atomic_write import atomic_write_json

log = logging.getLogger(__name__)

_CORPUS_PROJECTION_KEYS = (
    "file_id",
    "date",
    "language",
    "duration_s",
    "processed_at",
    "pipeline_version",
    "polish_engine",
    "overlap_ratio",
    "source_codec",
    "source_bitrate",
    "mfa_aligned",
    "processed_at_db_state",
)


def load() -> list[dict]:
    """Read corpus.json; return [] if absent or unreadable."""
    if not CORPUS_FILE.exists():
        return []
    try:
        with open(CORPUS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.error("corpus.json unreadable: %s", exc)
        return []
    if not isinstance(data, list):
        log.error("corpus.json has unexpected shape: %s", type(data).__name__)
        return []
    return data


def _save(entries: list[dict]) -> None:
    atomic_write_json(CORPUS_FILE, entries)


def append_session(entry: dict) -> None:
    """Atomically append one session to corpus.json."""
    entries = load()
    entries.append(entry)
    _save(entries)


def replace_session(file_id: str, entry: dict) -> None:
    """Overwrite the prior entry for `file_id`, or append if absent. Used by --redo."""
    entries = [e for e in load() if e.get("file_id") != file_id]
    entries.append(entry)
    _save(entries)


def find(file_id: str) -> dict | None:
    """Return the entry matching `file_id` or None."""
    for e in load():
        if e.get("file_id") == file_id:
            return e
    return None


def session_entry_from(transcript: dict) -> dict:
    """Project a full polished transcript down to a corpus entry."""
    entry = {k: transcript[k] for k in _CORPUS_PROJECTION_KEYS if k in transcript}
    for p in transcript.get("participants") or []:
        role = p.get("role")
        if role == "teacher":
            entry["teacher_id"] = p.get("id")
        elif role == "student":
            entry["student_id"] = p.get("id")
    return entry


def reconcile_from_polished() -> int:
    """
    Scan POLISHED_DIR for transcripts whose file_id is absent from corpus.json
    and append corpus entries for them. Returns the number of entries added.

    Guards against a crash between stage3.finalize's two writes (polished
    JSON then corpus update). On next startup, run.preflight calls this to
    replay orphan entries before any normal processing.

    Single read + single write of corpus.json regardless of orphan count.
    """
    if not POLISHED_DIR.exists():
        return 0

    entries = load()
    indexed = {e.get("file_id") for e in entries if e.get("file_id")}
    to_add: list[dict] = []

    for polished in sorted(POLISHED_DIR.glob("*.json")):
        file_id = polished.stem
        if file_id in indexed:
            continue
        try:
            with open(polished, "r", encoding="utf-8") as fh:
                transcript = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("reconcile: skipping %s (%s)", polished.name, exc)
            continue
        entry = session_entry_from(transcript)
        if not entry.get("teacher_id") and not entry.get("student_id"):
            log.warning(
                "reconcile: %s has no teacher_id/student_id - likely missing "
                "'participants' field; indexing with partial metadata",
                polished.name,
            )
        to_add.append(entry)
        log.info("reconcile: re-indexed orphan polished %s", file_id)

    if to_add:
        _save(entries + to_add)
    return len(to_add)
