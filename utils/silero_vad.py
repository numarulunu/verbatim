"""
Silero VAD wrapper.

Generates a speech mask before Whisper runs. Cuts ~90% of
"Thank you for watching"-class hallucinations by never feeding Whisper
the silent regions that induce them.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def load_model():
    """Lazy-instantiate the Silero VAD model (CPU, lightweight)."""
    raise NotImplementedError


def speech_mask(audio: "np.ndarray", sr: int) -> "np.ndarray":
    """Return a boolean per-sample (or per-frame) speech mask."""
    raise NotImplementedError


def speech_timestamps(audio: "np.ndarray", sr: int) -> list[dict]:
    """Return [{'start': s, 'end': s}, ...] with merged regions <VAD_MERGE_GAP_MS apart."""
    raise NotImplementedError
