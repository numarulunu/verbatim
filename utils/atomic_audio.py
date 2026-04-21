"""
Atomic soundfile write.

Same pattern as utils.atomic_write but for WAV: write to <path>.tmp with
soundfile, fsync, os.replace into place. A crash between the write and the
rename leaves the original <path> untouched (soundfile writes to the .tmp
only — never to the real path).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import soundfile as sf


def atomic_write_wav(
    path: Path,
    audio: np.ndarray,
    sr: int,
    subtype: str = "PCM_16",
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    try:
        sf.write(str(tmp), audio, sr, subtype=subtype)
        # soundfile doesn't expose fsync; open r+b for a writable fd (needed on Windows).
        with open(tmp, "r+b") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
