"""
CPU decode worker — ffmpeg → 16 kHz mono float32 numpy array.

Runs inside a ProcessPoolExecutor. Must be picklable. Errors raised here
are surfaced to the orchestrator, never swallowed.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def decode(source: Path) -> "np.ndarray":
    """Extract audio from `source`, resample to 16 kHz mono, return float32 PCM."""
    raise NotImplementedError


def probe_duration(source: Path) -> float:
    """Return duration in seconds using ffprobe."""
    raise NotImplementedError


def worker_init() -> None:
    """ProcessPool initializer — pins worker to P-cores, sets logging."""
    raise NotImplementedError
