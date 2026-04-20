"""
Audio quality checks.

Applied after vocal isolation and before Whisper:

  spectral_gate(audio, sr, floor_db)
      STFT -> zero magnitudes below floor_db relative to peak -> iSTFT.
      Kills harmonic ghosts left by MelBand on sustained sung notes that
      otherwise trigger Whisper hallucinations on "silent" piano harmonics.

  overlap_ratio(diarization, duration_s)
      Fraction of wall-clock where two pyannote clusters are active at once.
      Logged in corpus.json. Files with >5% are flagged for manual review.

  clipping_ratio(audio)
      Digital-clipping sanity metric.

  source_codec_info(path)
      ffprobe -> {'codec', 'bitrate'}. Logged in corpus.json so we can trace
      whether a noisy source was re-encoded (WebM/Opus at low bitrate tends
      to underperform MP4/AAC for speech).
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)


def spectral_gate(
    audio: "np.ndarray",
    sr: int,
    floor_db: float,
    n_fft: int = 1024,
    hop_length: int = 256,
) -> "np.ndarray":
    """Zero STFT bins below `floor_db` relative to each frame's peak."""
    import numpy as np

    if audio.ndim != 1:
        raise ValueError(f"spectral_gate expects 1-D audio, got shape {audio.shape}")
    if len(audio) < n_fft:
        return audio.astype(np.float32, copy=True)

    # Lazy librosa import — keeps this module cheap to import in tests.
    import librosa

    stft = librosa.stft(audio, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(stft)
    # Per-frame peak in dB, then gate relative to it.
    peak = mag.max(axis=0, keepdims=True) + 1e-9
    mag_db = 20.0 * np.log10((mag + 1e-9) / peak)
    keep = mag_db >= floor_db
    stft_gated = stft * keep
    out = librosa.istft(stft_gated, hop_length=hop_length, length=len(audio))
    return out.astype(np.float32, copy=False)


def overlap_ratio(diarization, duration_s: float) -> float:
    """
    Fraction of `duration_s` where two distinct speakers are active at once.

    Accepts either a whisperx diarize DataFrame (columns start/end/speaker) or
    a pyannote Annotation. Returns 0.0 if duration is zero or unparseable.
    """
    if duration_s <= 0.0:
        return 0.0

    intervals_by_speaker: dict[str, list[tuple[float, float]]] = {}

    # whisperx DataFrame path
    if hasattr(diarization, "iterrows"):
        for _, row in diarization.iterrows():
            spk = str(row.get("speaker"))
            intervals_by_speaker.setdefault(spk, []).append(
                (float(row["start"]), float(row["end"]))
            )
    # pyannote Annotation path
    elif hasattr(diarization, "itertracks"):
        for segment, _, speaker in diarization.itertracks(yield_label=True):
            intervals_by_speaker.setdefault(str(speaker), []).append(
                (float(segment.start), float(segment.end))
            )
    else:
        log.warning(
            "overlap_ratio: unknown diarization shape %s; returning 0",
            type(diarization).__name__,
        )
        return 0.0

    speakers = list(intervals_by_speaker.keys())
    if len(speakers) < 2:
        return 0.0

    total_overlap = 0.0
    for i, a in enumerate(speakers):
        for b in speakers[i + 1:]:
            for a_s, a_e in intervals_by_speaker[a]:
                for b_s, b_e in intervals_by_speaker[b]:
                    lo = max(a_s, b_s)
                    hi = min(a_e, b_e)
                    if hi > lo:
                        total_overlap += hi - lo
    return min(1.0, total_overlap / duration_s)


def clipping_ratio(audio: "np.ndarray", threshold: float = 0.995) -> float:
    """Fraction of samples at or above `threshold` absolute magnitude."""
    import numpy as np
    if audio.size == 0:
        return 0.0
    return float(np.mean(np.abs(audio) >= threshold))


def source_codec_info(path: Path) -> dict:
    """Return {'codec': str, 'bitrate': int_or_None} via ffprobe."""
    path = Path(path)
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,bit_rate:format=bit_rate",
        "-of", "json",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        data = json.loads(out)
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError) as exc:
        log.warning("ffprobe failed for %s: %s", path, exc)
        return {"codec": None, "bitrate": None}

    stream = (data.get("streams") or [{}])[0]
    codec = stream.get("codec_name")
    br = stream.get("bit_rate") or data.get("format", {}).get("bit_rate")
    try:
        bitrate = int(br) if br is not None else None
    except (ValueError, TypeError):
        bitrate = None
    return {"codec": codec, "bitrate": bitrate}
