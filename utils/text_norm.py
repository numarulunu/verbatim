"""
Text normalization.

Primary use: turn Romanian display names into ASCII `id` fields.
  "Mădălina"  → "madalina"
  "Ionuț"     → "ionut"
  "Ștefan R." → "stefan_r"
"""
from __future__ import annotations


def ascii_id(name: str) -> str:
    """NFKD normalize → strip diacritics → lowercase → underscore non-alnum."""
    raise NotImplementedError


def display_with_disambiguator(display_name: str, disambiguator: str | None) -> str:
    """Return 'Name' or 'Name (R.)' depending on whether disambiguator is set."""
    raise NotImplementedError


def is_valid_id(candidate: str) -> bool:
    """Enforce ^[a-z0-9_]+$ and non-empty."""
    raise NotImplementedError
