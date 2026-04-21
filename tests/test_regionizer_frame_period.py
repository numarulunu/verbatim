"""
_has_sustained_pitch's frame-period must match the extractor (pyworld 10ms
vs librosa ~32ms at sr=16000). Otherwise the SUSTAIN_MIN_SECONDS check
fires at the wrong frame count.
"""
import numpy as np


def test_frame_s_is_10ms_for_pyworld(monkeypatch):
    from persons import regionizer

    monkeypatch.setattr(regionizer, "PITCH_EXTRACTOR", "pyworld")

    # 1.5s of stable 440 Hz at pyworld 10ms frames = 150 samples.
    n_frames = 150
    f0 = np.full(n_frames, 440.0, dtype=np.float32)

    # With correct 10ms frame_s, 150 frames × 10ms = 1.5s >= SUSTAIN_MIN_SECONDS.
    # The function MUST detect sustained pitch. If frame_s is stuck at 32ms,
    # it would need 150 frames × 32ms = 4.8s and return False.
    assert regionizer._has_sustained_pitch(f0, frame_s=0.010, min_duration_s=1.5)


def test_frame_s_is_sr_derived_for_librosa(monkeypatch):
    from persons import regionizer

    monkeypatch.setattr(regionizer, "PITCH_EXTRACTOR", "librosa")

    # 1.5s of stable 440 Hz at librosa 32ms frames = ~47 samples.
    n_frames = 47
    f0 = np.full(n_frames, 440.0, dtype=np.float32)

    frame_s = 512.0 / 16000  # 0.032
    assert regionizer._has_sustained_pitch(f0, frame_s, 1.5)


def test_classify_segment_uses_correct_frame_period(monkeypatch):
    """classify_segment -> _has_sustained_pitch passes a frame_s that
    matches PITCH_EXTRACTOR, not the hardcoded librosa 32ms value. With the
    bug present (hardcoded 32ms), 48 frames of pyworld output are counted as
    48 × 32ms = 1.54s and falsely trigger sung_full (real duration is
    48 × 10ms = 0.48s, below the 1.5s threshold)."""
    from persons import regionizer

    monkeypatch.setattr(regionizer, "PITCH_EXTRACTOR", "pyworld")

    def fake_pitch(audio, sr):
        # 48 frames = 0.48s at pyworld's real 10ms — below SUSTAIN_MIN_SECONDS
        return np.full(48, 440.0, dtype=np.float32)

    monkeypatch.setattr(regionizer, "extract_pitch", fake_pitch)
    audio = np.zeros(16000 * 2, dtype=np.float32)
    label = regionizer.classify_segment(audio, sr=16000, person=None)
    assert label != "sung_full", (
        f"bug: classify_segment returned sung_full for 48 pyworld frames (0.48s real); "
        f"should only trigger at >=150 frames. Got: {label!r}"
    )
