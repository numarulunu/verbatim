"""
Phase 2 tests for the decode-time hardening wired into stage2.transcribe().

faster-whisper isn't loaded in CI; we monkeypatch load_whisper() to return a
fake pipeline that records the kwargs each transcribe call received. That
lets us assert the hardening hooks fire (or don't) per the config flags
without touching CUDA.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# --------------------------------------------------------------------------- #
# Fake faster-whisper pipeline
# --------------------------------------------------------------------------- #

class _FakeWord:
    def __init__(self, start: float, end: float, word: str, probability: float | None = 0.9) -> None:
        self.start = start
        self.end = end
        self.word = word
        self.probability = probability


class _FakeSegment:
    def __init__(
        self,
        start: float,
        end: float,
        text: str,
        avg_logprob: float = -0.2,
        no_speech_prob: float = 0.05,
        words: list[_FakeWord] | None = None,
    ) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob
        self.words = words


class _FakeInfo:
    def __init__(self, language: str = "ro") -> None:
        self.language = language


class _FakePipe:
    """Records every transcribe() call's kwargs + returns canned segments."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append({"audio_shape": audio.shape, **kwargs})
        seg = _FakeSegment(
            0.0, 1.5, " hello world",
            words=[_FakeWord(0.0, 0.5, " hello"), _FakeWord(0.6, 1.4, " world", 0.55)],
        )
        return iter([seg]), _FakeInfo()


@pytest.fixture
def fake_pipe(monkeypatch):
    fake = _FakePipe()
    import stage2_transcribe_diarize as s2
    monkeypatch.setattr(s2, "load_whisper", lambda: fake)
    # Skip the spectral floor + LUFS ops so we don't need librosa STFT here.
    monkeypatch.setattr(
        "utils.audio_preprocess.adaptive_spectral_floor",
        lambda a, sr: a,
    )
    return fake


@pytest.fixture
def short_audio() -> np.ndarray:
    rng = np.random.default_rng(0)
    return (0.05 * rng.standard_normal(16_000 * 2)).astype(np.float32)


# --------------------------------------------------------------------------- #
# Phase 2 hardening assertions
# --------------------------------------------------------------------------- #

def test_word_timestamps_always_on(fake_pipe, short_audio) -> None:
    """Phase 4 prerequisite. Must be true regardless of config calibration."""
    from stage2_transcribe_diarize import transcribe

    transcribe(short_audio, language="ro", vad_timestamps=None)
    assert fake_pipe.calls[0]["word_timestamps"] is True


def test_suppress_tokens_only_passed_when_calibrated(fake_pipe, short_audio, monkeypatch) -> None:
    """SUPPRESS_TOKENS_FOR_SUNG=None → kwarg absent (Phase 1 not committed)."""
    import stage2_transcribe_diarize as s2

    monkeypatch.setattr(s2, "SUPPRESS_TOKENS_FOR_SUNG", None)
    s2.transcribe(short_audio, language="ro", vad_timestamps=None)
    assert "suppress_tokens" not in fake_pipe.calls[0]

    fake_pipe.calls.clear()
    monkeypatch.setattr(s2, "SUPPRESS_TOKENS_FOR_SUNG", (50361, 50362, 50363))
    s2.transcribe(short_audio, language="ro", vad_timestamps=None)
    assert fake_pipe.calls[0]["suppress_tokens"] == [50361, 50362, 50363]


def test_compression_ratio_threshold_only_passed_when_calibrated(
    fake_pipe, short_audio, monkeypatch
) -> None:
    import stage2_transcribe_diarize as s2

    monkeypatch.setattr(s2, "COMPRESSION_RATIO_THRESHOLD", None)
    s2.transcribe(short_audio, language="ro", vad_timestamps=None)
    assert "compression_ratio_threshold" not in fake_pipe.calls[0]

    fake_pipe.calls.clear()
    monkeypatch.setattr(s2, "COMPRESSION_RATIO_THRESHOLD", 1.8)
    s2.transcribe(short_audio, language="ro", vad_timestamps=None)
    assert fake_pipe.calls[0]["compression_ratio_threshold"] == 1.8


def test_segments_carry_per_segment_metadata(fake_pipe, short_audio) -> None:
    """rms_dbfs, vad_coverage_ratio, and words[] all populated per segment."""
    from stage2_transcribe_diarize import transcribe

    out = transcribe(
        short_audio,
        language="ro",
        vad_timestamps=[{"start": 0.0, "end": 1.5}],
    )
    assert len(out["segments"]) == 1
    seg = out["segments"][0]
    assert "rms_dbfs" in seg
    assert "vad_coverage_ratio" in seg
    assert seg["vad_coverage_ratio"] == 1.0  # full overlap
    assert "words" in seg
    assert len(seg["words"]) == 2
    assert seg["words"][1]["probability"] == 0.55


def test_lufs_normalize_only_when_target_set(fake_pipe, short_audio, monkeypatch) -> None:
    """File-level LUFS norm is a no-op when LUFS_TARGET is None."""
    import stage2_transcribe_diarize as s2

    calls = []
    monkeypatch.setattr(
        "utils.audio_preprocess.normalize_lufs",
        lambda a, sr, target_lufs: calls.append(target_lufs) or a,
    )

    monkeypatch.setattr(s2, "LUFS_TARGET", None)
    s2.transcribe(short_audio, language="ro", vad_timestamps=None)
    assert calls == []  # not called

    calls.clear()
    monkeypatch.setattr(s2, "LUFS_TARGET", -20.0)
    s2.transcribe(short_audio, language="ro", vad_timestamps=None)
    assert calls == [-20.0]


def test_clip_timestamps_converted_to_sample_indices(fake_pipe, short_audio) -> None:
    """faster-whisper expects clip_timestamps in samples, not seconds."""
    from stage2_transcribe_diarize import transcribe

    transcribe(
        short_audio,
        language="ro",
        vad_timestamps=[{"start": 0.5, "end": 1.5}],
    )
    clips = fake_pipe.calls[0]["clip_timestamps"]
    assert clips == [{"start": 8000, "end": 24000}]
