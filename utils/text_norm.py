"""
Text normalization.

Primary use: turn Romanian display names into ASCII `id` fields.
  "Mădălina"  → "madalina"
  "Ionuț"     → "ionut"
  "Ștefan R." → "stefan_r"
"""
from __future__ import annotations

import re
import unicodedata

_ID_CHAR_RE = re.compile(r"[^a-z0-9]+")
_VALID_ID_RE = re.compile(r"^[a-z0-9_]+$")


def ascii_id(name: str) -> str:
    """NFKD normalize → strip diacritics → lowercase → underscore non-alnum runs."""
    if not name:
        raise ValueError("ascii_id: empty input")
    stripped = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    normalized = _ID_CHAR_RE.sub("_", stripped.lower()).strip("_")
    if not normalized:
        raise ValueError(f"ascii_id: no ASCII characters survived in {name!r}")
    return normalized


def display_with_disambiguator(display_name: str, disambiguator: str | None) -> str:
    """Return 'Name' or 'Name (R.)' depending on whether disambiguator is set."""
    if disambiguator:
        return f"{display_name} ({disambiguator})"
    return display_name


def is_valid_id(candidate: str) -> bool:
    """Enforce ^[a-z0-9_]+$ and non-empty."""
    return bool(candidate) and bool(_VALID_ID_RE.match(candidate))
