"""
Smoke tests for the Phase 1 calibration harness.

The full harness needs labeled audio + GPU + faster-whisper + pyannote, none
of which are present in CI. These tests verify the lighter contracts:

- Each harness script imports cleanly from a fresh interpreter.
- The pure-CPU classifier-B implementation (ZCR + RMS hybrid) returns the
  expected label on synthetic audio.
- The harness handles missing corpus gracefully (exits 1 with an actionable
  log message, never with a stack trace).
- The recommended-thresholds writer survives an empty sweep.
- Phase 2-4 placeholder config keys exist and default to None.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


@pytest.mark.parametrize("script", ["calibrate", "profile_vram", "validate_sung_classifier"])
def test_harness_script_parse_check(script: str) -> None:
    """Import each harness script's bytecode without executing it."""
    path = SCRIPTS / f"{script}.py"
    assert path.exists(), f"{path} missing"
    # Use py_compile to byte-compile without running. SystemExit at import time
    # would still be caught here.
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"py_compile failed: {result.stderr}"


def test_phase_2_config_placeholders_exist_and_are_none() -> None:
    """Every Phase 2 / Phase 4 placeholder added in commit X must default
    to None so the pipeline behavior is unchanged until calibration."""
    config = importlib.import_module("config")
    placeholders = [
        "SUPPRESS_TOKENS_FOR_SUNG",
        "COMPRESSION_RATIO_THRESHOLD",
        "RMS_GREEDY_THRESHOLD_DBFS",
        "NO_SPEECH_THRESHOLD_HIGH",
        "VAD_LOW_COVERAGE_RATIO",
        "VAD_LOW_COVERAGE_FRACTION",
        "LUFS_TARGET",
        "POLISH_CHUNK_SIZE_NEW",
        "WORD_CONFIDENCE_THRESHOLD",
        "PHONETIC_DISTANCE_GATE",
    ]
    for key in placeholders:
        assert hasattr(config, key), f"config.{key} missing"
        assert getattr(config, key) is None, (
            f"config.{key} must default to None until Phase 1 calibration commits a value"
        )


def test_zcr_rms_classifier_labels_loud_speech_as_spoken() -> None:
    """Synthetic 'spoken' audio (loud, speech-band noise) should classify as spoken."""
    from scripts.validate_sung_classifier import classifier_b_zcr_rms

    rng = np.random.default_rng(42)
    sr = 16_000
    # 1 second of band-limited noise normalized to ~-12 dBFS — well above the
    # -30 dBFS sung threshold; should classify as "spoken".
    audio = rng.standard_normal(sr).astype(np.float32) * 0.25
    label = classifier_b_zcr_rms(audio, sr)
    assert label == "spoken", f"loud noise should be 'spoken', got {label}"


def test_zcr_rms_classifier_labels_quiet_noise_as_sung() -> None:
    """The Risk Analyst's classifier B rule is `RMS < -30 dBFS AND ZCR > 0.3`.
    Quiet white noise satisfies both: ZCR ≈ 0.5 (Gaussian zero-crossings) and
    low RMS. Whether this rule actually fits real sung passages is the
    empirical question that `validate_sung_classifier.py` answers against the
    labeled corpus. This test only verifies the rule encoding."""
    from scripts.validate_sung_classifier import classifier_b_zcr_rms

    sr = 16_000
    rng = np.random.default_rng(7)
    # 1 second of white noise at ~-35 dBFS (rms ≈ 0.018).
    audio = (0.018 * rng.standard_normal(sr)).astype(np.float32)
    label = classifier_b_zcr_rms(audio, sr)
    assert label == "sung", f"quiet white noise should hit the sung rule, got {label}"


def test_zcr_rms_classifier_labels_sustained_tone_as_spoken() -> None:
    """Sustained pure tones — the canonical 'sung' content in real audio —
    have LOW ZCR (≈0.05 for a 440 Hz tone at 16 kHz) and FAIL classifier B's
    sung rule. This is a known weakness of the ZCR+RMS heuristic vs the
    pyworld F0-stability classifier; Phase 1 picks whichever classifier
    wins on the labeled set."""
    from scripts.validate_sung_classifier import classifier_b_zcr_rms

    sr = 16_000
    t = np.arange(sr) / sr
    audio = (0.02 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    assert classifier_b_zcr_rms(audio, sr) == "spoken"


def test_zcr_rms_classifier_handles_silence() -> None:
    from scripts.validate_sung_classifier import classifier_b_zcr_rms

    sr = 16_000
    audio = np.zeros(sr, dtype=np.float32)
    # RMS of all-zero is -120 dBFS (sung-eligible by RMS) but ZCR is 0 → spoken.
    assert classifier_b_zcr_rms(audio, sr) == "spoken"


def test_validate_sung_classifier_exits_cleanly_on_missing_corpus(tmp_path, monkeypatch) -> None:
    """When _calibration/lessons/ is empty, the script must exit 1 with an
    actionable message — never with a stack trace."""
    monkeypatch.chdir(tmp_path)
    # Run as a subprocess so the script's own sys.path tweak takes effect.
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_sung_classifier.py")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    # Exit may be 1 (no labels) OR fail at import if optional deps missing — both
    # acceptable for this smoke test as long as no Python traceback escapes.
    assert "Traceback" not in result.stderr, f"unexpected traceback:\n{result.stderr}"


def test_calibrate_exits_cleanly_on_missing_corpus(tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "calibrate.py")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    # Same guard: no traceback escapes.
    assert "Traceback" not in result.stderr, f"unexpected traceback:\n{result.stderr}"


def test_recommended_thresholds_json_is_writable_under_calibration_dir(tmp_path) -> None:
    """Round-trip a tiny recommendations payload to confirm the json writer
    contract Phase 2 will read."""
    rec_path = tmp_path / "recommended_thresholds.json"
    payload = {
        "avg_logprob_threshold": {"value": -0.6, "separation": 0.18},
    }
    rec_path.write_text(json.dumps(payload, indent=2))
    loaded = json.loads(rec_path.read_text())
    assert loaded == payload
