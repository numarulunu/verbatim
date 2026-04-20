"""
Silero VAD wrapper.

Generates a speech-timestamp list before Whisper runs. Cuts ~90% of
"Thank you for watching"-class hallucinations by never feeding the ASR
the silent regions that induce them.

Uses silero-vad v6 pip package (preferred) with a torch.hub fallback.
Runs on CPU — VAD is lightweight and keeping it off GPU avoids blocking
the Whisper / separator work.

Post-processing: adjacent speech regions whose gap is shorter than
VAD_MERGE_GAP_MS are glued into one. This is faithful to brief §6 phase 5
("VAD + post-VAD merge glues segments <2s apart"): the silero call itself
uses the SHORT `min_silence_duration_ms` so we don't miss pauses, and the
merge pass collapses lesson-relevant gaps back together.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import (
    VAD_MERGE_GAP_MS,
    VAD_MIN_SILENCE_MS,
    VAD_MIN_SPEECH_MS,
    VAD_THRESHOLD,
)

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)

_model = None


def load_model():
    """Lazy-load the Silero VAD model (CPU). Singleton per process."""
    global _model
    if _model is not None:
        return _model
    # Per silero-vad README: single-thread inference is the recommended path.
    # Multi-threading this CPU model causes intermittent RNN state corruption
    # (observed as `select(): index 1 out of range` crashes on certain clips).
    import torch
    torch.set_num_threads(1)
    try:
        from silero_vad import load_silero_vad
        _model = load_silero_vad()
        log.info("loaded silero-vad via pip package")
        return _model
    except ImportError:
        _model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
        )
        log.info("loaded silero-vad via torch.hub fallback")
        return _model


def speech_timestamps(audio: "np.ndarray", sr: int = 16000) -> list[dict]:
    """
    Return [{'start': float_s, 'end': float_s}, ...] with merged close regions.

    `audio` must be 1-D mono float32. `sr` is expected to be 16000 — silero is
    trained on that rate. Timestamps are in seconds (not samples).
    """
    import torch
    from silero_vad import get_speech_timestamps

    model = load_model()
    # Reset the model's internal RNN state between files so residual state from
    # a previous clip doesn't corrupt this one's pass.
    reset = getattr(model, "reset_states", None)
    if callable(reset):
        reset()
    wav = torch.from_numpy(audio).float() if not hasattr(audio, "dim") else audio
    raw = get_speech_timestamps(
        wav,
        model,
        threshold=VAD_THRESHOLD,
        sampling_rate=sr,
        min_speech_duration_ms=VAD_MIN_SPEECH_MS,
        min_silence_duration_ms=VAD_MIN_SILENCE_MS,
        return_seconds=True,
    )
    merged = _merge_close(raw, VAD_MERGE_GAP_MS)
    if raw and not merged:
        log.warning("silero returned %d regions but merge collapsed them all", len(raw))
    log.info("silero VAD: %d raw -> %d merged speech regions", len(raw), len(merged))
    return merged


def speech_mask(audio: "np.ndarray", sr: int = 16000) -> "np.ndarray":
    """
    Return a boolean mask, one value per sample, True inside speech regions.

    Called by callers that want per-sample gating rather than ranges.
    """
    import numpy as np
    mask = np.zeros(len(audio), dtype=bool)
    for span in speech_timestamps(audio, sr=sr):
        start = int(span["start"] * sr)
        end = min(int(span["end"] * sr), len(audio))
        if end > start:
            mask[start:end] = True
    return mask


def _merge_close(timestamps: list[dict], gap_ms: int) -> list[dict]:
    """Glue adjacent speech spans whose silence-gap is shorter than `gap_ms`."""
    if not timestamps:
        return []
    gap_s = gap_ms / 1000.0
    merged = [dict(timestamps[0])]
    for t in timestamps[1:]:
        if t["start"] - merged[-1]["end"] < gap_s:
            merged[-1]["end"] = t["end"]
        else:
            merged.append(dict(t))
    return merged
