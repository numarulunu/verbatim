"""
Parse session metadata from filenames.

Priority:
  1. session_map.json manual overrides
  2. YYYY-MM-DD_<teacher_id>__<student_id>_<lang>.<ext>   (double underscore)
  3. YYYY-MM-DD_<student_id>_<lang>.<ext>                 (legacy; teacher = DEFAULT_TEACHER_ID)

IDs are ASCII-lowercase (diacritics stripped via utils.text_norm).
Language must be in SUPPORTED_LANGUAGES or parse fails.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionMeta:
    date: str          # ISO YYYY-MM-DD
    language: str      # "en" | "ro"
    teacher_id: str
    student_id: str
    source_path: Path


def parse(path: Path) -> SessionMeta:
    """Resolve session metadata from a filename, consulting session_map.json first."""
    raise NotImplementedError


def load_session_map() -> dict[str, dict]:
    """Read session_map.json if present; return {} otherwise."""
    raise NotImplementedError


def _parse_double_underscore(stem: str, source: Path) -> SessionMeta | None:
    """Try the canonical YYYY-MM-DD_<teacher>__<student>_<lang> form."""
    raise NotImplementedError


def _parse_legacy(stem: str, source: Path) -> SessionMeta | None:
    """Try legacy single-name form; fills teacher with DEFAULT_TEACHER_ID."""
    raise NotImplementedError
