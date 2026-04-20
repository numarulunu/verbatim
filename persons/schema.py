"""
Person record schema.

Three parallel identifiers per person:
  id            — ASCII lowercase, filesystem-safe, DB key
  display_name  — full with diacritics (e.g., "Mădălina")
  disambiguator — suffix rendered after display_name when two persons share one

Filenames always use `id`. Transcripts render `display_name` (+ disambiguator
if present).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PersonRecord:
    id: str
    display_name: str
    disambiguator: str | None = None
    default_role: str = "student"           # "teacher" | "student"
    voice_type: str | None = None           # bass | baritone | tenor | alto | mezzo | soprano
    fach: str | None = None                 # lirico | drammatico | leggero | spinto | buffo
    n_sessions_as_teacher: int = 0
    n_sessions_as_student: int = 0
    first_seen: str | None = None           # ISO YYYY-MM-DD
    last_updated: str | None = None
    total_hours: float = 0.0
    observed_regions: list[str] = field(default_factory=list)
    region_session_counts: dict[str, int] = field(default_factory=dict)
    pitch_range_hz: tuple[float, float] | None = None
    collisions: list[str] = field(default_factory=list)


def to_dict(p: PersonRecord) -> dict:
    """Serialize a PersonRecord to JSON-safe dict."""
    raise NotImplementedError


def from_dict(d: dict) -> PersonRecord:
    """Deserialize from metadata.json."""
    raise NotImplementedError


def render_display(p: PersonRecord) -> str:
    """Return 'Display' or 'Display (Disambiguator)' depending on record."""
    raise NotImplementedError
