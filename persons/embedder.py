"""
Speaker embedding — pyannote/embedding, INT8-quantized via CTranslate2.

Pascal-native INT8 path. Returns 512-dim L2-normalized vectors.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def load_embedder():
    """Lazy-instantiate the INT8-quantized embedding model. Requires HF_TOKEN."""
    raise NotImplementedError


def embed(audio: "np.ndarray") -> "np.ndarray":
    """Compute a 512-dim L2-normalized embedding for a mono 16 kHz PCM array."""
    raise NotImplementedError


def embed_turn(audio: "np.ndarray", start_s: float, end_s: float) -> "np.ndarray":
    """Slice a turn from audio and embed it."""
    raise NotImplementedError


def cosine(a: "np.ndarray", b: "np.ndarray") -> float:
    """Cosine similarity between two pre-normalized vectors (plain dot product)."""
    raise NotImplementedError


def teardown() -> None:
    """Release embedder resources."""
    raise NotImplementedError
