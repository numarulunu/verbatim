"""
Short-turn verification pass.

For every turn shorter than VERIFICATION_MAX_TURN_SECONDS, embed the turn
itself and compare against both cluster centroids. If the OTHER cluster
wins by more than VERIFICATION_REASSIGN_MARGIN in cosine, flip the label.

This module takes an `embed_fn` parameter rather than importing the
embedder directly — keeps it free of torch/pyannote at import time, which
makes it unit-testable without the full ML stack.
"""
from __future__ import annotations

import logging
from typing import Callable

import numpy as np

from config import VERIFICATION_MAX_TURN_SECONDS, VERIFICATION_REASSIGN_MARGIN

log = logging.getLogger(__name__)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a_n = a / (np.linalg.norm(a) + 1e-9)
    b_n = b / (np.linalg.norm(b) + 1e-9)
    return float(np.dot(a_n, b_n))


def verify_turn(
    turn_embedding: np.ndarray,
    assigned_cluster_centroid: np.ndarray,
    other_cluster_centroid: np.ndarray,
    margin: float = VERIFICATION_REASSIGN_MARGIN,
) -> bool:
    """True iff flipping to the other cluster would increase cosine by >margin."""
    if turn_embedding.ndim != 1:
        raise ValueError(
            f"turn_embedding must be 1-D, got shape {turn_embedding.shape}"
        )
    assigned = _cosine(turn_embedding, assigned_cluster_centroid)
    other = _cosine(turn_embedding, other_cluster_centroid)
    return (other - assigned) > margin


def verify_transcript(
    segments: list[dict],
    cluster_embeddings: dict[str, np.ndarray],
    embed_fn: Callable[[np.ndarray, int], np.ndarray],
    audio: np.ndarray,
    sr: int,
) -> list[dict]:
    """
    Scan short segments; reassign where warranted. Returns a NEW list.

    Each input segment must carry a `cluster_label` that matches a key in
    `cluster_embeddings`. Flipped segments have their `cluster_label` swapped
    to the other key and gain a `_verifier_flipped: True` marker — the caller
    is responsible for re-resolving speaker_id/name/role from the updated
    cluster label (see stage3_postprocess).
    """
    if not segments or len(cluster_embeddings) != 2:
        return list(segments)

    labels = list(cluster_embeddings.keys())
    out: list[dict] = []
    flips = 0

    for seg in segments:
        dur = seg["end"] - seg["start"]
        if dur >= VERIFICATION_MAX_TURN_SECONDS:
            out.append(seg)
            continue
        start_idx = int(seg["start"] * sr)
        end_idx = int(seg["end"] * sr)
        if end_idx <= start_idx or end_idx > len(audio):
            out.append(seg)
            continue
        clip = audio[start_idx:end_idx]
        try:
            emb = embed_fn(clip, sr)
        except Exception as exc:  # noqa: BLE001 — verifier is best-effort
            log.debug(
                "embed failed for turn [%.2f-%.2f]: %s",
                seg["start"], seg["end"], exc,
            )
            out.append(seg)
            continue

        current_label = seg.get("cluster_label")
        if current_label not in cluster_embeddings:
            out.append(seg)
            continue
        other_label = next(l for l in labels if l != current_label)

        should_flip = verify_turn(
            emb,
            cluster_embeddings[current_label],
            cluster_embeddings[other_label],
        )
        if should_flip:
            new_seg = dict(seg)
            new_seg["cluster_label"] = other_label
            new_seg["_verifier_flipped"] = True
            out.append(new_seg)
            flips += 1
        else:
            out.append(seg)

    if flips:
        log.info("verifier flipped %d / %d short turns", flips, len(segments))
    return out
