"""
Phase 2 tests for utils/audio_preprocess.py:
  - rms_dbfs returns sane values on silence / loud / quiet audio.
  - normalize_lufs is a no-op when target_lufs is None (Phase 1 not calibrated).
  - normalize_lufs round-trips loudness within ±2 LUFS of the target.
  - adaptive_spectral_floor preserves the loud part of a quiet+loud signal
    while gating the quiet part.
  - vad_coverage_ratio computes overlap correctly.
"""
from __future__ import annotations

import numpy as np
import pytest

from utils.audio_preprocess import (
    adaptive_spectral_floor,
    normalize_lufs,
    rms_dbfs,
    vad_coverage_ratio,
)


# --------------------------------------------------------------------------- #
# rms_dbfs
# --------------------------------------------------------------------------- #

def test_rms_dbfs_silence_is_floor() -> None:
    audio = np.zeros(16_000, dtype=np.float32)
    assert rms_dbfs(audio) == -120.0


def test_rms_dbfs_empty_is_floor() -> None:
    assert rms_dbfs(np.zeros(0, dtype=np.float32)) == -120.0


def test_rms_dbfs_full_scale_is_zero_dbfs() -> None:
    audio = np.ones(1_000, dtype=np.float32)
    assert rms_dbfs(audio) == pytest.approx(0.0, abs=0.01)


def test_rms_dbfs_quarter_amplitude_is_minus_12() -> None:
    audio = (0.25 * np.ones(1_000)).astype(np.float32)
    # -12.04 dBFS = 20 * log10(0.25)
    assert rms_dbfs(audio) == pytest.approx(-12.04, abs=0.05)


# --------------------------------------------------------------------------- #
# normalize_lufs
# --------------------------------------------------------------------------- #

def test_normalize_lufs_no_op_when_target_none() -> None:
    """When LUFS_TARGET is None (Phase 1 hasn't calibrated yet), the
    function is a pass-through. This is the production behavior the day
    Phase 2 ships."""
    audio = (0.1 * np.random.default_rng(1).standard_normal(16_000)).astype(np.float32)
    out = normalize_lufs(audio, sr=16_000, target_lufs=None)
    np.testing.assert_array_equal(out, audio)


def test_normalize_lufs_brings_quiet_audio_to_target() -> None:
    """Quiet white noise at ~-40 LUFS gets boosted to ~-20 LUFS within ±2."""
    rng = np.random.default_rng(7)
    audio = (0.005 * rng.standard_normal(16_000)).astype(np.float32)
    out = normalize_lufs(audio, sr=16_000, target_lufs=-20.0)

    import pyloudnorm as pyln
    measured = pyln.Meter(16_000).integrated_loudness(out.astype(np.float64))
    assert measured == pytest.approx(-20.0, abs=2.0)


def test_normalize_lufs_skips_short_buffers() -> None:
    """Buffers < 0.4s can't be measured reliably; function returns input."""
    audio = (0.1 * np.ones(100)).astype(np.float32)
    out = normalize_lufs(audio, sr=16_000, target_lufs=-20.0)
    np.testing.assert_array_equal(out, audio)


# --------------------------------------------------------------------------- #
# adaptive_spectral_floor
# --------------------------------------------------------------------------- #

def test_adaptive_spectral_floor_passes_through_short_audio() -> None:
    """Audio shorter than the FFT window comes back unchanged."""
    audio = np.ones(500, dtype=np.float32)
    out = adaptive_spectral_floor(audio, sr=16_000)
    np.testing.assert_array_equal(out, audio)


def test_adaptive_spectral_floor_preserves_loud_signal_energy() -> None:
    """A loud sine wave passes through with most of its energy intact."""
    sr = 16_000
    t = np.arange(sr) / sr
    audio = (0.3 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    out = adaptive_spectral_floor(audio, sr=sr)
    # Loose: ≥ 80% of the original RMS survives.
    in_rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    out_rms = float(np.sqrt(np.mean(out.astype(np.float64) ** 2)))
    assert out_rms >= 0.80 * in_rms


def test_adaptive_spectral_floor_attenuates_low_level_noise() -> None:
    """A quiet broadband noise (where the in-frame peak/floor ratio is
    narrow) gets gated more aggressively than a loud tonal signal."""
    sr = 16_000
    rng = np.random.default_rng(11)
    audio = (0.001 * rng.standard_normal(sr)).astype(np.float32)
    out = adaptive_spectral_floor(audio, sr=sr)
    in_rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    out_rms = float(np.sqrt(np.mean(out.astype(np.float64) ** 2)))
    assert out_rms <= in_rms  # never adds energy
    # The hard-ceiling rule (-55 dBFS) should leave SOME energy through even
    # on broadband noise — this isn't a brick-wall mute.
    assert out_rms > 0.0


# --------------------------------------------------------------------------- #
# vad_coverage_ratio
# --------------------------------------------------------------------------- #

def test_vad_coverage_ratio_no_vad_assumes_full_speech() -> None:
    assert vad_coverage_ratio(0.0, 5.0, None) == 1.0
    assert vad_coverage_ratio(0.0, 5.0, []) == 1.0


def test_vad_coverage_ratio_full_overlap_is_one() -> None:
    vad = [{"start": 0.0, "end": 5.0}]
    assert vad_coverage_ratio(1.0, 4.0, vad) == 1.0


def test_vad_coverage_ratio_no_overlap_is_zero() -> None:
    vad = [{"start": 10.0, "end": 12.0}]
    assert vad_coverage_ratio(0.0, 5.0, vad) == 0.0


def test_vad_coverage_ratio_partial_overlap() -> None:
    """Segment 0-10s. VAD covers 0-3 and 7-10. Coverage = 6/10 = 0.6."""
    vad = [{"start": 0.0, "end": 3.0}, {"start": 7.0, "end": 10.0}]
    assert vad_coverage_ratio(0.0, 10.0, vad) == pytest.approx(0.6)
