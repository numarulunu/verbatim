"""
Region-aware cluster → person matching.

Scoring: for each (cluster, person) pair, take MAX cosine across every
region centroid plus each row of the recent-buffer ring. Assign the two
pyannote clusters to persons to maximize total score.

Session role (teacher/student) comes from the filename, not the matcher.
A person with no voice library yet scores -1, so the OTHER cluster is
always assigned to a known participant and the orphan cluster is the
bootstrap fingerprint for the new person.
"""
from __future__ import annotations

import logging

import numpy as np

from config import COLLISION_THRESHOLD
from persons.registry import (
    PersonNotFoundError,
    list_all,
    person_dir,
    register_new,
)
from persons.schema import PersonRecord

log = logging.getLogger(__name__)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a_n = a / (np.linalg.norm(a) + 1e-9)
    b_n = b / (np.linalg.norm(b) + 1e-9)
    return float(np.dot(a_n, b_n))


def load_voice_library(person: PersonRecord) -> dict[str, np.ndarray]:
    """Return {region_name_or_'recent_or_universal': ndarray} for every centroid on disk."""
    pdir = person_dir(person.id)
    library: dict[str, np.ndarray] = {}
    if not pdir.exists():
        return library
    for npy in pdir.glob("*.npy"):
        try:
            library[npy.stem] = np.load(npy)
        except (ValueError, OSError) as exc:
            log.warning("could not load %s: %s", npy, exc)
    return library


def best_match_score(
    cluster_embedding: np.ndarray,
    library: dict[str, np.ndarray],
) -> tuple[float, str]:
    """Return (max cosine, winning centroid name) across a library. (-1.0, '') if empty."""
    if not library:
        return (-1.0, "")
    best_score = -1.0
    best_name = ""
    for name, centroid in library.items():
        if centroid.ndim == 1:
            score = _cosine(cluster_embedding, centroid)
            if score > best_score:
                best_score, best_name = score, name
        elif centroid.ndim == 2:
            # recent.npy is a ring of (N, D) past universals.
            for row in centroid:
                score = _cosine(cluster_embedding, row)
                if score > best_score:
                    best_score, best_name = score, name
    return (best_score, best_name)


def assign_clusters(
    cluster_embeddings: dict[str, np.ndarray],
    teacher: PersonRecord | None,
    student: PersonRecord | None,
) -> dict[str, tuple[str, float, str]]:
    """
    Resolve {cluster_label: (person_id, confidence, matched_region)}.

    Tries both possible (teacher_label, student_label) assignments, picks the
    one with higher total score. Clusters assigned to unregistered participants
    (teacher=None or student=None) are omitted from the result — the caller
    bootstraps them.
    """
    labels = list(cluster_embeddings.keys())
    if len(labels) != 2:
        raise ValueError(f"expected exactly 2 clusters, got {labels}")

    t_lib = load_voice_library(teacher) if teacher else {}
    s_lib = load_voice_library(student) if student else {}

    scores: dict[str, dict[str, tuple[float, str]]] = {}
    for label, emb in cluster_embeddings.items():
        scores[label] = {
            "teacher": best_match_score(emb, t_lib),
            "student": best_match_score(emb, s_lib),
        }

    c1, c2 = labels
    option_a = scores[c1]["teacher"][0] + scores[c2]["student"][0]
    option_b = scores[c1]["student"][0] + scores[c2]["teacher"][0]
    if option_a >= option_b:
        teacher_label, student_label = c1, c2
    else:
        teacher_label, student_label = c2, c1

    out: dict[str, tuple[str, float, str]] = {}
    if teacher is not None:
        conf, region = scores[teacher_label]["teacher"]
        out[teacher_label] = (teacher.id, conf, region)
    if student is not None:
        conf, region = scores[student_label]["student"]
        out[student_label] = (student.id, conf, region)
    return out


def bootstrap_new_person(
    bootstrap_embedding: np.ndarray,
    id_: str,
    display_name: str,
    default_role: str,
    first_seen: str,
) -> PersonRecord:
    """
    Create a fresh person record whose bootstrap fingerprint is this session's cluster.

    Saves `universal.npy` (1-D) and `recent.npy` (1 × D ring buffer) immediately
    so a subsequent session can already match against this person.
    """
    record = register_new(
        id_=id_,
        display_name=display_name,
        default_role=default_role,
        first_seen=first_seen,
    )
    pdir = person_dir(record.id)
    pdir.mkdir(parents=True, exist_ok=True)
    emb = bootstrap_embedding / (np.linalg.norm(bootstrap_embedding) + 1e-9)
    np.save(pdir / "universal.npy", emb)
    np.save(pdir / "recent.npy", emb.reshape(1, -1))
    return record


def check_collisions() -> list[tuple[str, str, float]]:
    """Return all person-pairs whose universal cosine > COLLISION_THRESHOLD."""
    universals: dict[str, np.ndarray] = {}
    for p in list_all():
        u = person_dir(p.id) / "universal.npy"
        if u.exists():
            try:
                universals[p.id] = np.load(u)
            except (ValueError, OSError) as exc:
                log.warning("skipping %s.universal: %s", p.id, exc)
    ids = list(universals.keys())
    pairs: list[tuple[str, str, float]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            cos = _cosine(universals[a], universals[b])
            if cos > COLLISION_THRESHOLD:
                pairs.append((a, b, cos))
    return pairs


__all__ = [
    "assign_clusters",
    "best_match_score",
    "bootstrap_new_person",
    "check_collisions",
    "load_voice_library",
    "PersonNotFoundError",
]
