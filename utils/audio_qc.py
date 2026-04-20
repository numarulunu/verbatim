"""
Audio quality checks.

Applied after vocal isolation and before Whisper:
  - spectral_gate: zero frequency bins below SPECTRAL_GATE_DB to kill
                   harmonic ghosts left by MelBand on sustained notes.
  - overlap_ratio: measure simultaneous-speech fraction, logged in
                   corpus.json. Files >5% flagged for manual review.
  - clipping_ratio: sanity metric per file.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def spectral_gate(audio: "np.ndarray", sr: int, floor_db: float) -> "np.ndarray":
    """STFT → zero bins below floor_db → iSTFT."""
    raise NotImplementedError


def overlap_ratio(diarization: dict, duration_s: float) -> float:
    """Fraction of duration where two speakers are active simultaneously."""
    raise NotImplementedError


def clipping_ratio(audio: "np.ndarray") -> float:
    """Fraction of samples at or near ±1.0 (digital clipping)."""
    raise NotImplementedError


def source_codec_info(path: Path) -> dict:
    """Return {'codec': ..., 'bitrate': ...} via ffprobe. Logged in corpus.json."""
    raise NotImplementedError
