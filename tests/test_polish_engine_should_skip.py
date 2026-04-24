"""
Phase 4 test for the updated should_skip() in persons/polish_engine.py.

Verifies the routing logic:
  - When WORD_CONFIDENCE_THRESHOLD is None (Phase 1 not committed), legacy
    avg_logprob behavior is preserved.
  - When WORD_CONFIDENCE_THRESHOLD is set AND the segment has a `words`
    list, the gate is per-word (skip iff every word ≥ threshold).
  - Sung segments (set by sung_handler) always skip.
  - Segments with WORD_CONFIDENCE_THRESHOLD set but no `words` field fall
    through to the legacy gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import persons.polish_engine as _pe
from persons.polish_engine import should_skip


def _seg_with_logprob(logprob: float, words=None) -> dict:
    seg = {"avg_logprob": logprob}
    if words is not None:
        seg["words"] = words
    return seg


# --------------------------------------------------------------------------- #
# Legacy avg_logprob path (WORD_CONFIDENCE_THRESHOLD is None)
# --------------------------------------------------------------------------- #

def test_legacy_path_skips_high_confidence_segment(monkeypatch) -> None:
    monkeypatch.setattr(_pe, "WORD_CONFIDENCE_THRESHOLD", None)
    monkeypatch.setattr(_pe, "POLISH_SKIP_AVG_LOGPROB", -0.3)
    assert should_skip(_seg_with_logprob(-0.2)) is True


def test_legacy_path_polishes_low_confidence_segment(monkeypatch) -> None:
    monkeypatch.setattr(_pe, "WORD_CONFIDENCE_THRESHOLD", None)
    monkeypatch.setattr(_pe, "POLISH_SKIP_AVG_LOGPROB", -0.3)
    assert should_skip(_seg_with_logprob(-0.5)) is False


# --------------------------------------------------------------------------- #
# Word-level path (WORD_CONFIDENCE_THRESHOLD set)
# --------------------------------------------------------------------------- #

def test_word_level_skips_when_every_word_above_threshold(monkeypatch) -> None:
    seg = _seg_with_logprob(
        -0.5,
        words=[{"word": "a", "probability": 0.9}, {"word": "b", "probability": 0.8}],
    )
    monkeypatch.setattr(_pe, "WORD_CONFIDENCE_THRESHOLD", 0.6)
    assert should_skip(seg) is True


def test_word_level_polishes_when_any_word_below_threshold(monkeypatch) -> None:
    seg = _seg_with_logprob(
        -0.1,  # legacy gate would skip; word-level overrides
        words=[{"word": "a", "probability": 0.9}, {"word": "b", "probability": 0.4}],
    )
    monkeypatch.setattr(_pe, "WORD_CONFIDENCE_THRESHOLD", 0.6)
    assert should_skip(seg) is False


def test_word_level_falls_back_to_legacy_when_no_words_field(monkeypatch) -> None:
    """Calibrated threshold but no per-word data → legacy avg_logprob path."""
    seg = _seg_with_logprob(-0.2)
    monkeypatch.setattr(_pe, "WORD_CONFIDENCE_THRESHOLD", 0.6)
    monkeypatch.setattr(_pe, "POLISH_SKIP_AVG_LOGPROB", -0.3)
    assert should_skip(seg) is True  # logprob -0.2 > -0.3


# --------------------------------------------------------------------------- #
# Sung segments
# --------------------------------------------------------------------------- #

def test_sung_segments_always_skip(monkeypatch) -> None:
    """sung_handler tags segments with polished=True + sung=True; polish must
    pass them through untouched."""
    seg = {"text": "[SUNG: ~5s]", "polished": True, "sung": True}
    monkeypatch.setattr(_pe, "WORD_CONFIDENCE_THRESHOLD", None)
    assert should_skip(seg) is True
    monkeypatch.setattr(_pe, "WORD_CONFIDENCE_THRESHOLD", 0.6)
    assert should_skip(seg) is True
