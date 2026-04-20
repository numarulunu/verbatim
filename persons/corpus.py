"""
Corpus index — corpus.json.

One entry per processed session:
  {
    "file_id":        "2024-03-15_ionut__madalina_en",
    "date":           "2024-03-15",
    "language":       "en",
    "teacher_id":     "ionut",
    "student_id":     "madalina",
    "duration_s":     3120.1,
    "processed_at":   "...Z",
    "pipeline_version": "1.0.0",
    "polish_engine":  "cli",
    "overlap_ratio":  0.03,
    "source_codec":   "aac",
    "source_bitrate": 128000
  }
"""
from __future__ import annotations

from pathlib import Path


def load() -> list[dict]:
    """Read corpus.json; return [] if absent."""
    raise NotImplementedError


def append_session(entry: dict) -> None:
    """Atomically append one session to corpus.json."""
    raise NotImplementedError


def replace_session(file_id: str, entry: dict) -> None:
    """Used by --redo to overwrite a prior session entry."""
    raise NotImplementedError


def session_entry_from(transcript: dict) -> dict:
    """Project a full polished transcript down to a corpus entry."""
    raise NotImplementedError
