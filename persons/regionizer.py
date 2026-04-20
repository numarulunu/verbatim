"""
Pitch-based vocal region classifier.

Classifies each segment of a person's audio into:
  speaking   — low pitch variance, narrow range in speech F0 band
  sung_low   — musical content, median pitch in the person's low band
  sung_mid   — mid band
  sung_high  — high band
  sung_full  — pitch held stable for >SUSTAIN_MIN_SECONDS

Bands are PERSON-RELATIVE — a bass's "high" is not a soprano's "high".
First session uses voice-type heuristics; later sessions refine from the
person's own observed pitch distribution.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from persons.schema import PersonRecord

if TYPE_CHECKING:
    import numpy as np


def extract_pitch(audio: "np.ndarray", sr: int) -> "np.ndarray":
    """Return F0 contour in Hz (pyworld or librosa per config.PITCH_EXTRACTOR)."""
    raise NotImplementedError


def classify_segment(
    audio: "np.ndarray",
    sr: int,
    person: PersonRecord | None,
) -> str:
    """Return one of REGION_LABELS for a single audio segment."""
    raise NotImplementedError


def segment_by_region(
    audio: "np.ndarray",
    sr: int,
    person: PersonRecord | None,
) -> dict[str, list[tuple[float, float]]]:
    """Group contiguous frames into region → [(start_s, end_s), ...]."""
    raise NotImplementedError


def update_pitch_range(person: PersonRecord, f0_hz: "np.ndarray") -> None:
    """Expand person.pitch_range_hz with observations from a new session."""
    raise NotImplementedError


def default_bands_for_voice_type(voice_type: str | None) -> dict[str, tuple[float, float]]:
    """Heuristic Hz bands when a person has no observed pitch data yet."""
    raise NotImplementedError
