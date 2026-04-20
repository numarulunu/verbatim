"""
Person registry — filesystem-backed lookup by id.

Layout under VOICEPRINT_DIR:
  people/
    <id>/
      metadata.json
      universal.npy
      speaking.npy
      sung_*.npy
      recent.npy
"""
from __future__ import annotations

from pathlib import Path

from persons.schema import PersonRecord


def load(person_id: str) -> PersonRecord:
    """Load a person record; raises KeyError if absent."""
    raise NotImplementedError


def save(p: PersonRecord) -> None:
    """Atomic-write the person record back to metadata.json."""
    raise NotImplementedError


def exists(person_id: str) -> bool:
    """True if people/<id>/metadata.json is present."""
    raise NotImplementedError


def list_all() -> list[PersonRecord]:
    """Enumerate every registered person."""
    raise NotImplementedError


def register_new(
    id_: str,
    display_name: str,
    default_role: str,
    disambiguator: str | None = None,
    voice_type: str | None = None,
) -> PersonRecord:
    """Create a new record. Refuses display_name collision without disambiguator."""
    raise NotImplementedError


def person_dir(person_id: str) -> Path:
    """Absolute path to a person's voiceprint directory."""
    raise NotImplementedError


def rename(old_id: str, new_id: str) -> None:
    """Rename id across filesystem, transcripts, and corpus.json."""
    raise NotImplementedError


def merge(id1: str, id2: str, keep: str) -> None:
    """Merge two records; `keep` is the id to retain."""
    raise NotImplementedError
