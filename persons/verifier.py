"""
Short-turn verification pass.

For every turn shorter than VERIFICATION_MAX_TURN_SECONDS, embed the turn
itself and compare against both cluster centroids. If the OTHER cluster
wins by more than VERIFICATION_REASSIGN_MARGIN in cosine, flip the label.

~10% compute overhead on the identification stage. Disable via
SPEAKER_VERIFICATION_ENABLED = False.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def verify_turn(
    turn_audio: "np.ndarray",
    assigned_cluster_centroid: "np.ndarray",
    other_cluster_centroid: "np.ndarray",
    margin: float,
) -> bool:
    """Return True if the other cluster matches by >margin → caller should flip label."""
    raise NotImplementedError


def verify_transcript(
    segments: list[dict],
    cluster_embeddings: dict[str, "np.ndarray"],
    audio: "np.ndarray",
    sr: int,
) -> list[dict]:
    """Scan all short segments; reassign where warranted. Returns updated segments."""
    raise NotImplementedError
