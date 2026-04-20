"""
Stage 1 — vocal isolation.

Uses `audio-separator` with MelBand Roformer to strip the heavy background
piano that runs through every vocal lesson. Output is saved to
ACAPELLA_DIR/<file_id>.wav. Idempotent: skips files whose acapella already
exists.

Post-separation: -40 dB spectral gate to kill residual harmonic ghosts that
would otherwise trigger Whisper hallucinations.
"""
from __future__ import annotations

from pathlib import Path


def isolate_batch(sources: list[Path]) -> list[Path]:
    """Run vocal isolation over a batch; return output paths. Tears down VRAM on completion."""
    raise NotImplementedError


def isolate_one(source: Path) -> Path:
    """Single-file vocal isolation. Skips if acapella already exists."""
    raise NotImplementedError


def spectral_gate(wav_path: Path, floor_db: float) -> None:
    """In-place spectral gate: zero bins below floor_db. Kills harmonic ghosts."""
    raise NotImplementedError


def teardown_separator() -> None:
    """Release VRAM held by the separator model before next GPU stage."""
    raise NotImplementedError
