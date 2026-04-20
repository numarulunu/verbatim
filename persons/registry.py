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

import json
import logging
import shutil
from pathlib import Path

from config import VOICEPRINT_DIR
from persons.schema import PersonRecord, from_dict, to_dict
from utils.atomic_write import atomic_write_json
from utils.text_norm import is_valid_id

log = logging.getLogger(__name__)


class DuplicateDisplayNameError(ValueError):
    """Second person with the same display_name needs an explicit --disambiguator."""


class PersonNotFoundError(KeyError):
    """Registry has no record for this id."""


def _people_root() -> Path:
    root = VOICEPRINT_DIR / "people"
    root.mkdir(parents=True, exist_ok=True)
    return root


def person_dir(person_id: str) -> Path:
    """Absolute path to a person's voiceprint directory (not guaranteed to exist)."""
    return _people_root() / person_id


def _metadata_path(person_id: str) -> Path:
    return person_dir(person_id) / "metadata.json"


def exists(person_id: str) -> bool:
    """True if people/<id>/metadata.json is present."""
    return _metadata_path(person_id).exists()


def load(person_id: str) -> PersonRecord:
    """Load a person record; raises PersonNotFoundError if absent."""
    path = _metadata_path(person_id)
    if not path.exists():
        raise PersonNotFoundError(person_id)
    with open(path, "r", encoding="utf-8") as fh:
        return from_dict(json.load(fh))


def save(p: PersonRecord) -> None:
    """Atomic-write the record to people/<id>/metadata.json."""
    person_dir(p.id).mkdir(parents=True, exist_ok=True)
    atomic_write_json(_metadata_path(p.id), to_dict(p))


def list_all() -> list[PersonRecord]:
    """Enumerate every registered person in lexicographic id order."""
    out: list[PersonRecord] = []
    root = _people_root()
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        try:
            out.append(load(d.name))
        except (PersonNotFoundError, OSError, json.JSONDecodeError) as exc:
            log.warning("skipping %s: %s", d.name, exc)
    return out


def register_new(
    id_: str,
    display_name: str,
    default_role: str,
    disambiguator: str | None = None,
    voice_type: str | None = None,
    fach: str | None = None,
    first_seen: str | None = None,
) -> PersonRecord:
    """Create a new record. Refuses display_name collision without disambiguator."""
    if not is_valid_id(id_):
        raise ValueError(f"invalid id {id_!r}: must match ^[a-z0-9_]+$")
    if default_role not in ("teacher", "student"):
        raise ValueError(
            f"default_role must be 'teacher' or 'student', got {default_role!r}"
        )
    if exists(id_):
        raise ValueError(f"person {id_!r} already exists")
    # Same-display-name collision requires explicit disambiguator on the NEW entry.
    # The first person with that display_name never gets an auto-disambiguator.
    if disambiguator is None:
        for other in list_all():
            if other.display_name == display_name:
                raise DuplicateDisplayNameError(
                    f"display_name {display_name!r} already used by {other.id!r}; "
                    "pass --disambiguator to register a second person"
                )
    record = PersonRecord(
        id=id_,
        display_name=display_name,
        disambiguator=disambiguator,
        default_role=default_role,
        voice_type=voice_type,
        fach=fach,
        first_seen=first_seen,
    )
    save(record)
    log.info("registered person %r (display=%r)", id_, display_name)
    return record


def rename(old_id: str, new_id: str) -> None:
    """Rename the id on disk. Transcripts + corpus.json rewrite via `run.py --redo --all`."""
    if not is_valid_id(new_id):
        raise ValueError(f"invalid new id {new_id!r}")
    if not exists(old_id):
        raise PersonNotFoundError(old_id)
    if exists(new_id):
        raise ValueError(f"target id {new_id!r} already exists")
    old_dir = person_dir(old_id)
    new_dir = person_dir(new_id)
    shutil.move(str(old_dir), str(new_dir))
    record = load(new_id)
    record.id = new_id
    save(record)
    log.warning(
        "renamed %s -> %s. Transcripts still reference the old id - "
        "run `python run.py --redo --all` to rewrite them.",
        old_id, new_id,
    )


def merge(id1: str, id2: str, keep: str) -> None:
    """Merge two records; `keep` is the id to retain. Voiceprints NOT averaged."""
    if keep not in (id1, id2):
        raise ValueError(f"keep must be one of {id1!r}, {id2!r}")
    if not (exists(id1) and exists(id2)):
        raise PersonNotFoundError(f"{id1} or {id2} missing")
    drop = id2 if keep == id1 else id1
    keeper = load(keep)
    dropped = load(drop)
    keeper.n_sessions_as_teacher += dropped.n_sessions_as_teacher
    keeper.n_sessions_as_student += dropped.n_sessions_as_student
    keeper.total_hours += dropped.total_hours
    for region in dropped.observed_regions:
        if region not in keeper.observed_regions:
            keeper.observed_regions.append(region)
    for region, count in dropped.region_session_counts.items():
        keeper.region_session_counts[region] = (
            keeper.region_session_counts.get(region, 0) + count
        )
    save(keeper)
    shutil.rmtree(person_dir(drop))
    log.warning(
        "merged %s into %s. Voiceprint centroids were NOT averaged - "
        "the dropped library was discarded. Run `--redo --all` to rebuild.",
        drop, keep,
    )


def flag_collision(id1: str, id2: str) -> None:
    """Record a pairwise collision in both persons' metadata (idempotent)."""
    if id1 == id2:
        return
    for a, b in ((id1, id2), (id2, id1)):
        try:
            rec = load(a)
        except PersonNotFoundError:
            continue
        if b not in rec.collisions:
            rec.collisions.append(b)
            save(rec)
