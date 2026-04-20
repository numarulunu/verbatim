"""
CPU decode worker — ffmpeg → 16 kHz mono float32 numpy array.

Runs inside a ProcessPoolExecutor. Workers are pinned to P-cores via
`worker_init` so ffmpeg children inherit affinity.

ffmpeg errors raise CalledProcessError and are surfaced to the orchestrator.
We DO NOT catch-and-swallow: one bad file should be logged by run.py and
skipped, not masked at this level.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from config import DECODE_SAMPLE_RATE

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)


def decode(source: Path) -> "np.ndarray":
    """Extract audio, resample to 16 kHz mono, return float32 PCM."""
    import numpy as np

    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(source)

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-loglevel", "error",
        "-i", str(source),
        "-f", "f32le",
        "-ac", "1",
        "-ar", str(DECODE_SAMPLE_RATE),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise RuntimeError(f"ffmpeg returned empty audio for {source}")
    return audio.copy()  # detach from immutable bytes buffer


def probe_duration(source: Path) -> float:
    """Return duration in seconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(source),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def worker_init() -> None:
    """ProcessPool initializer — pins worker to P-cores before any decoding."""
    # Local import: the worker process starts fresh and must re-initialize.
    from hw_clamp import pin_to_p_cores
    pin_to_p_cores()
    # Silence stdlib logging noise from workers — they communicate through the
    # orchestrator's progress reporting, not their own stdout.
    logging.getLogger().setLevel(logging.WARNING)
