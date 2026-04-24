"""
audio_preprocess — Phase 2 per-segment audio shaping for Whisper.

Three primitives:

  rms_dbfs(audio)
      Pure-numpy RMS in dBFS. Used by the decode-time temperature ramp
      (config.RMS_GREEDY_THRESHOLD_DBFS) and by the adaptive spectral floor.

  normalize_lufs(audio, sr, target_lufs)
      ITU-R BS.1770-4 loudness normalization to a constant target. Whisper
      is trained on normalized audio; per-segment normalization eliminates
      the decoder-uncertainty spikes that occur when loudness varies
      session-to-session or speaker-to-speaker within a session.
      Target defaults to config.LUFS_TARGET when None.

  adaptive_spectral_floor(audio, sr)
      Per-segment replacement for stage1's global -40 dB spectral_gate.
      The global gate sets a noise floor based on the loudest frames in
      the file — fine for music but ruins quiet teacher-coaching speech
      that's adjacent to a sustained sung note. Per-segment estimates the
      noise floor from the bottom 5th percentile of frame RMS within the
      segment and gates 6 dB above that. A hard ceiling of -55 dBFS keeps
      pristine studio recordings from being over-gated.

All functions are pure numpy / pyloudnorm — no torch, no GPU. Safe to call
inside the per-segment Whisper loop.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


_NEAR_SILENCE_DBFS = -120.0
_NOISE_FLOOR_PERCENTILE = 5.0
_NOISE_FLOOR_HEADROOM_DB = 6.0
_HARD_CEILING_DBFS = -55.0


def rms_dbfs(audio: "np.ndarray") -> float:
    """Whole-buffer RMS in dBFS. Returns -120.0 for silence/all-zero."""
    import numpy as np

    if audio.size == 0:
        return _NEAR_SILENCE_DBFS
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if rms <= 0.0:
        return _NEAR_SILENCE_DBFS
    return 20.0 * float(np.log10(rms))


def normalize_lufs(
    audio: "np.ndarray",
    sr: int,
    target_lufs: float | None = None,
) -> "np.ndarray":
    """LUFS-normalize a buffer to `target_lufs`. Defaults to config.LUFS_TARGET
    when target_lufs is None; if THAT is also None (Phase 1 not yet calibrated),
    returns the input unchanged."""
    import numpy as np

    if target_lufs is None:
        from config import LUFS_TARGET
        target_lufs = LUFS_TARGET
    if target_lufs is None:
        return audio  # Phase 1 not calibrated yet — no-op.

    if audio.size == 0:
        return audio

    # pyloudnorm needs >= 0.4 s @ 16 kHz to compute integrated loudness reliably.
    min_samples = int(round(0.4 * sr))
    if audio.size < min_samples:
        return audio

    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    try:
        loudness = meter.integrated_loudness(audio.astype(np.float64))
    except (ValueError, ZeroDivisionError):
        # Audio too short or all-silent — pyloudnorm can throw.
        return audio
    if not np.isfinite(loudness):
        return audio
    normalized = pyln.normalize.loudness(audio, loudness, target_lufs)
    # Cast back to original dtype.
    return normalized.astype(audio.dtype, copy=False)


def adaptive_spectral_floor(
    audio: "np.ndarray",
    sr: int,
    n_fft: int = 1024,
    hop_length: int = 256,
) -> "np.ndarray":
    """Per-segment replacement for the global stage1 spectral_gate.

    Estimates the segment-local noise floor from the bottom 5th-percentile of
    per-frame magnitudes; gates 6 dB above that. A hard ceiling of -55 dBFS
    relative to the per-frame peak prevents over-gating in pristine
    recordings. Returns audio with sub-floor frequency bins zeroed.
    """
    import numpy as np

    if audio.ndim != 1:
        raise ValueError(f"adaptive_spectral_floor expects 1-D audio, got shape {audio.shape}")
    if audio.size < n_fft:
        return audio.astype(np.float32, copy=True)

    import librosa

    stft = librosa.stft(audio, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(stft)
    peak = mag.max(axis=0, keepdims=True) + 1e-9
    mag_db = 20.0 * np.log10((mag + 1e-9) / peak)

    # Per-frame noise floor estimate: 5th-percentile of in-frame magnitudes (dB).
    floor_db_per_frame = np.percentile(mag_db, _NOISE_FLOOR_PERCENTILE, axis=0, keepdims=True)
    threshold_db = floor_db_per_frame + _NOISE_FLOOR_HEADROOM_DB
    # Hard ceiling: never gate above -55 dB relative to peak.
    threshold_db = np.minimum(threshold_db, _HARD_CEILING_DBFS)

    keep = mag_db >= threshold_db
    gated_stft = stft * keep
    gated_audio = librosa.istft(gated_stft, hop_length=hop_length, length=audio.size)
    return gated_audio.astype(np.float32, copy=False)


def vad_coverage_ratio(
    segment_start_s: float,
    segment_end_s: float,
    vad_timestamps: list[dict] | None,
) -> float:
    """Fraction of [segment_start_s, segment_end_s] that overlaps a Silero
    speech timestamp. Returns 1.0 when no VAD output is supplied (assume
    speech everywhere)."""
    if not vad_timestamps:
        return 1.0
    seg_dur = max(segment_end_s - segment_start_s, 1e-6)
    covered = 0.0
    for vad in vad_timestamps:
        v_start = float(vad["start"])
        v_end = float(vad["end"])
        overlap = max(0.0, min(v_end, segment_end_s) - max(v_start, segment_start_s))
        covered += overlap
    return min(covered / seg_dur, 1.0)
