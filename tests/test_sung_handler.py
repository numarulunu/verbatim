"""
Phase 3 tests for persons/sung_handler.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from persons.sung_handler import handle_sung


@pytest.fixture
def fake_audio() -> np.ndarray:
    return np.zeros(16_000 * 30, dtype=np.float32)


@pytest.fixture
def voice_libraries() -> dict[str, dict[str, np.ndarray]]:
    rng = np.random.default_rng(0)

    def _norm(v: np.ndarray) -> np.ndarray:
        return v / (np.linalg.norm(v) + 1e-9)

    return {
        "ionut": {"universal": _norm(rng.standard_normal(512).astype(np.float32))},
        "student_ana": {"universal": _norm(rng.standard_normal(512).astype(np.float32))},
    }


def test_handle_sung_replaces_text_with_marker(fake_audio, voice_libraries, monkeypatch) -> None:
    """Each sung segment loses its text in favor of `[SUNG: ~Xs]`."""
    # Stub embedder so we don't load pyannote/embedding for a unit test.
    fake_emb = list(voice_libraries["ionut"].values())[0]
    monkeypatch.setattr("persons.embedder.embed_turn", lambda audio, s, e: fake_emb)

    segs = [
        {"start": 0.0, "end": 5.0, "text": "fake whisper output", "region": "sung_full",
         "speaker_id": "ionut", "words": [{"start": 0.1, "end": 0.4, "word": "ah"}]},
        {"start": 5.0, "end": 8.0, "text": "more fake", "region": "sung_high",
         "speaker_id": "ionut"},
    ]
    out = handle_sung(segs, fake_audio, 16_000, voice_libraries)
    assert out[0]["text"] == "[SUNG: ~5s]"
    assert out[1]["text"] == "[SUNG: ~3s]"
    assert all(s["polished"] is True for s in out)
    assert all(s["sung"] is True for s in out)
    # Per-word data dropped on sung segments.
    assert "words" not in out[0]


def test_handle_sung_passes_through_spoken(fake_audio, voice_libraries, monkeypatch) -> None:
    """Segments without a sung region are unchanged."""
    monkeypatch.setattr("persons.embedder.embed_turn", lambda audio, s, e: np.zeros(512))
    segs = [{"start": 0.0, "end": 1.0, "text": "spoken", "region": "speaking"}]
    out = handle_sung(segs, fake_audio, 16_000, voice_libraries)
    assert out[0]["text"] == "spoken"
    assert "sung" not in out[0]


def test_handle_sung_picks_best_cosine_speaker(fake_audio, voice_libraries, monkeypatch) -> None:
    """Per-segment embedding routed against the flattened library; closest
    centroid wins via best_match_score."""
    target_pid = "student_ana"
    target_vec = list(voice_libraries[target_pid].values())[0]
    monkeypatch.setattr("persons.embedder.embed_turn", lambda audio, s, e: target_vec)

    segs = [
        {"start": 0.0, "end": 4.0, "text": "x", "region": "sung_mid", "speaker_id": "ionut"},
    ]
    out = handle_sung(segs, fake_audio, 16_000, voice_libraries)
    assert out[0]["speaker_id"] == target_pid
    assert out[0]["speaker_confidence"] == pytest.approx(1.0, abs=1e-3)


def test_handle_sung_survives_empty_library(fake_audio, monkeypatch) -> None:
    """No voice library yet (e.g., first-ever bootstrap session) — sung
    handler still returns the marker, just keeps inherited speaker_id."""
    monkeypatch.setattr("persons.embedder.embed_turn", lambda audio, s, e: np.zeros(512))
    segs = [{"start": 0.0, "end": 2.0, "text": "x", "region": "sung_low", "speaker_id": "ionut"}]
    out = handle_sung(segs, fake_audio, 16_000, voice_libraries={})
    assert out[0]["text"] == "[SUNG: ~2s]"
    assert out[0]["speaker_id"] == "ionut"


def test_handle_sung_handles_too_short_segment(fake_audio, voice_libraries, monkeypatch) -> None:
    """Embedder needs >=0.5s audio — too-short segments must not crash the
    handler; they keep their inherited speaker label."""
    def _raise(*args, **kwargs):
        raise ValueError("audio too short for embedding")

    monkeypatch.setattr("persons.embedder.embed_turn", _raise)
    segs = [{"start": 0.0, "end": 0.1, "text": "x", "region": "sung_low", "speaker_id": "ionut"}]
    out = handle_sung(segs, fake_audio, 16_000, voice_libraries)
    assert out[0]["text"] == "[SUNG: ~0s]"
    assert out[0]["speaker_id"] == "ionut"
