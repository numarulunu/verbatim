"""
Parse session metadata from filenames.

Priority:
  1. session_map.json manual overrides
  2. YYYY-MM-DD_<teacher_id>__<student_id>_<lang>.<ext>   (canonical)
  3. YYYY-MM-DD_<student_id>_<lang>.<ext>                  (legacy, teacher
                                                            defaults to
                                                            DEFAULT_TEACHER_ID)

IDs are lowercase ASCII `[a-z0-9_]+`. Language must be in SUPPORTED_LANGUAGES
or parse fails. This module never writes — session_map.json is human-edited.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from config import DEFAULT_TEACHER_ID, SESSION_MAP_FILE, SUPPORTED_LANGUAGES

log = logging.getLogger(__name__)

_DOUBLE_UNDERSCORE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<teacher>[a-z0-9_]+?)__"
    r"(?P<student>[a-z0-9_]+?)_(?P<lang>[a-z]{2})$"
)

_LEGACY_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<student>[a-z0-9_]+?)_(?P<lang>[a-z]{2})$"
)


@dataclass(frozen=True)
class SessionMeta:
    date: str             # ISO YYYY-MM-DD
    language: str         # "en" | "ro"
    teacher_id: str
    student_id: str
    source_path: Path


class FilenameParseError(ValueError):
    """Raised when a filename cannot be mapped to a SessionMeta."""


def load_session_map() -> dict[str, dict]:
    """Read session_map.json if present; return {} otherwise."""
    if not SESSION_MAP_FILE.exists():
        return {}
    try:
        with open(SESSION_MAP_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("session_map.json unreadable (%s); ignoring", exc)
        return {}
    if not isinstance(data, dict):
        log.warning("session_map.json must be a dict; got %s", type(data).__name__)
        return {}
    return data


def parse(path: Path) -> SessionMeta:
    """Resolve session metadata for a source file."""
    path = Path(path)
    session_map = load_session_map()
    override = session_map.get(path.name)
    if override is not None:
        try:
            meta = SessionMeta(
                date=override["date"],
                language=override["language"],
                teacher_id=override["teacher_id"],
                student_id=override["student_id"],
                source_path=path,
            )
        except KeyError as exc:
            raise FilenameParseError(
                f"session_map.json entry for {path.name!r} missing key {exc}"
            ) from exc
        _validate(meta, path)
        return meta

    stem = path.stem.lower()
    meta = _parse_double_underscore(stem, path) or _parse_legacy(stem, path)
    if meta is None:
        raise FilenameParseError(
            f"cannot parse filename {path.name!r}; "
            "use YYYY-MM-DD_<teacher>__<student>_<lang>.<ext> or add an entry "
            "to session_map.json"
        )
    _validate(meta, path)
    return meta


def _validate(meta: SessionMeta, path: Path) -> None:
    if meta.language not in SUPPORTED_LANGUAGES:
        raise FilenameParseError(
            f"unsupported language {meta.language!r} in {path.name!r} "
            f"(supported: {SUPPORTED_LANGUAGES})"
        )


def _parse_double_underscore(stem: str, source: Path) -> SessionMeta | None:
    m = _DOUBLE_UNDERSCORE_RE.match(stem)
    if not m:
        return None
    return SessionMeta(
        date=m.group("date"),
        language=m.group("lang"),
        teacher_id=m.group("teacher"),
        student_id=m.group("student"),
        source_path=source,
    )


def _parse_legacy(stem: str, source: Path) -> SessionMeta | None:
    m = _LEGACY_RE.match(stem)
    if not m:
        return None
    return SessionMeta(
        date=m.group("date"),
        language=m.group("lang"),
        teacher_id=DEFAULT_TEACHER_ID,
        student_id=m.group("student"),
        source_path=source,
    )


def file_id(meta: SessionMeta) -> str:
    """Canonical file_id used for 02_raw_json/ and 03_polished/ output filenames."""
    return f"{meta.date}_{meta.teacher_id}__{meta.student_id}_{meta.language}"
