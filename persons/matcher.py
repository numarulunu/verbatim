"""
Region-aware cluster → person matching.

Scoring: for each (cluster, person) pair, take MAX cosine across every
region centroid plus each recent-buffer entry. Assign each of the two
pyannote clusters to the person with the higher max score.

Session role (teacher/student) comes from the filename, not the matcher.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from persons.schema import PersonRecord

if TYPE_CHECKING:
    import numpy as np


def load_voice_library(person: PersonRecord) -> dict[str, "np.ndarray"]:
    """Return {'universal', 'speaking', 'sung_low', ..., 'recent'} centroids from disk."""
    raise NotImplementedError


def best_match_score(
    cluster_embedding: "np.ndarray",
    library: dict[str, "np.ndarray"],
) -> tuple[float, str]:
    """Return (max cosine, winning region name) across every centroid in a library."""
    raise NotImplementedError


def assign_clusters(
    cluster_embeddings: dict[str, "np.ndarray"],
    teacher: PersonRecord | None,
    student: PersonRecord | None,
) -> dict[str, tuple[str, float, str]]:
    """Return {cluster_label: (person_id, confidence, matched_region)} for both clusters."""
    raise NotImplementedError


def bootstrap_new_person(
    bootstrap_embedding: "np.ndarray",
    id_: str,
    display_name: str,
    default_role: str,
    first_seen: str,
) -> PersonRecord:
    """Create fresh person record from a single session's cluster embedding."""
    raise NotImplementedError


def check_collisions() -> list[tuple[str, str, float]]:
    """Return all person-pairs whose universal cosine > COLLISION_THRESHOLD."""
    raise NotImplementedError
