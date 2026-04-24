"""
Phase 3 tests for utils/word_reattribute.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.word_reattribute import reattribute_words


def _norm(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-9)


@pytest.fixture
def fake_audio() -> np.ndarray:
    return np.zeros(16_000 * 30, dtype=np.float32)


@pytest.fixture
def two_speaker_libs() -> dict[str, dict[str, np.ndarray]]:
    rng = np.random.default_rng(42)
    return {
        "ionut": {"universal": _norm(rng.standard_normal(512).astype(np.float32))},
        "ana":   {"universal": _norm(rng.standard_normal(512).astype(np.float32))},
    }


def test_skips_when_only_one_speaker(fake_audio) -> None:
    """Need ≥ 2 voiceprints to compare; degenerate to no-op otherwise."""
    libs = {"ionut": {"universal": np.zeros(512, dtype=np.float32)}}
    segs = [{"start": 0, "end": 1, "speaker_id": "ionut",
             "words": [{"start": 0, "end": 0.5, "word": "hi"}]}]
    out = reattribute_words(segs, fake_audio, 16_000, libs)
    assert out == segs


def test_skips_sung_segments(fake_audio, two_speaker_libs, monkeypatch) -> None:
    monkeypatch.setattr(
        "persons.embedder.embed",
        lambda window: list(two_speaker_libs["ionut"].values())[0],
    )
    segs = [{"start": 0, "end": 4, "speaker_id": "ionut", "sung": True,
             "words": [{"start": 0, "end": 1, "word": "ah"}]}]
    out = reattribute_words(segs, fake_audio, 16_000, two_speaker_libs)
    assert "reattributed" not in out[0]


def test_skips_segments_without_words(fake_audio, two_speaker_libs) -> None:
    segs = [{"start": 0, "end": 1, "speaker_id": "ionut"}]
    out = reattribute_words(segs, fake_audio, 16_000, two_speaker_libs)
    assert "reattributed" not in out[0]


def test_flips_word_when_other_centroid_wins_by_margin(
    fake_audio, two_speaker_libs, monkeypatch
) -> None:
    """If the per-word embedding matches Ana's centroid by > margin while the
    segment is labeled Ionut, the word is flagged reattributed_to=ana."""
    ana_vec = list(two_speaker_libs["ana"].values())[0]
    monkeypatch.setattr("persons.embedder.embed", lambda window: ana_vec)

    segs = [
        {
            "start": 0.0, "end": 1.0,
            "speaker_id": "ionut",
            "speaker_confidence": 0.5,
            "words": [{"start": 0.0, "end": 1.0, "word": "ana"}],
        }
    ]
    out = reattribute_words(segs, fake_audio, 16_000, two_speaker_libs, margin=0.15)
    assert out[0]["reattributed"] is True
    assert out[0]["words"][0]["reattributed"] is True
    assert out[0]["words"][0]["reattributed_to"] == "ana"


def test_majority_word_flip_promotes_to_segment_label(
    fake_audio, two_speaker_libs, monkeypatch
) -> None:
    """Three of three words flip to ana → segment-level speaker_id flips too."""
    ana_vec = list(two_speaker_libs["ana"].values())[0]
    monkeypatch.setattr("persons.embedder.embed", lambda window: ana_vec)
    segs = [
        {
            "start": 0.0, "end": 3.0,
            "speaker_id": "ionut",
            "speaker_confidence": 0.4,
            "words": [
                {"start": 0.0, "end": 1.0, "word": "one"},
                {"start": 1.0, "end": 2.0, "word": "two"},
                {"start": 2.0, "end": 3.0, "word": "three"},
            ],
        }
    ]
    out = reattribute_words(segs, fake_audio, 16_000, two_speaker_libs)
    assert out[0]["speaker_id"] == "ana"
    assert out[0]["reattributed_segment_flip"] is True


def test_word_window_is_padded_to_min_500ms(
    fake_audio, two_speaker_libs, monkeypatch
) -> None:
    """Words shorter than 0.5 s get a symmetric pad so the embedder gets
    its required minimum window."""
    captured_windows = []

    def _spy_embed(window):
        captured_windows.append(window.size)
        return list(two_speaker_libs["ionut"].values())[0]

    monkeypatch.setattr("persons.embedder.embed", _spy_embed)
    segs = [{
        "start": 5.0, "end": 5.2,
        "speaker_id": "ionut",
        "speaker_confidence": 0.6,
        "words": [{"start": 5.0, "end": 5.2, "word": "hi"}],
    }]
    reattribute_words(segs, fake_audio, 16_000, two_speaker_libs)
    assert captured_windows
    assert captured_windows[0] >= 16_000 // 2  # ≥ 0.5 s
