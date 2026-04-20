"""Unit tests for `backend/core/diar_metrics.py`.

Synthetic fixtures only — no audio, no model loading. Must pass before the
10-clip labeling effort begins (plan sub-phase 1E).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.diar_metrics import (
    Turn,
    Word,
    cpwer,
    load_hyp_from_whisper_json,
    load_ref_from_json,
    speaker_purity,
    wder_decomposed,
)


def _w(text: str, start: float, end: float, speaker: str) -> Word:
    return Word(start=start, end=end, text=text, speaker=speaker)


# ---------------------------------------------------------------------------
# wder_decomposed
# ---------------------------------------------------------------------------

class TestWDERPerfect:
    def test_identical_sequences_score_zero(self):
        ref = [_w("hello", 0.0, 0.4, "S1"), _w("world", 0.4, 0.8, "S1")]
        hyp = [_w("hello", 0.0, 0.4, "A"), _w("world", 0.4, 0.8, "A")]
        res = wder_decomposed(ref, hyp)
        assert res.total == 0.0
        assert res.asr_component == 0.0
        assert res.assignment_component == 0.0
        assert res.n_ref == 2
        assert res.correct == 2

    def test_case_and_punctuation_insensitive(self):
        ref = [_w("Hello,", 0.0, 0.4, "S1")]
        hyp = [_w("hello", 0.0, 0.4, "A")]
        res = wder_decomposed(ref, hyp)
        assert res.asr_component == 0.0


class TestWDERASROnly:
    def test_single_substitution(self):
        ref = [_w("hello", 0.0, 0.4, "S1"), _w("world", 0.4, 0.8, "S1")]
        hyp = [_w("hello", 0.0, 0.4, "A"), _w("word", 0.4, 0.8, "A")]
        res = wder_decomposed(ref, hyp)
        assert res.substitutions == 1
        assert res.asr_component == pytest.approx(0.5)
        assert res.assignment_component == 0.0

    def test_deletion(self):
        ref = [_w("one", 0.0, 0.2, "S1"), _w("two", 0.2, 0.4, "S1"), _w("three", 0.4, 0.6, "S1")]
        hyp = [_w("one", 0.0, 0.2, "A"), _w("three", 0.4, 0.6, "A")]
        res = wder_decomposed(ref, hyp)
        assert res.deletions == 1
        assert res.asr_component == pytest.approx(1 / 3)

    def test_insertion(self):
        ref = [_w("one", 0.0, 0.2, "S1"), _w("two", 0.2, 0.4, "S1")]
        hyp = [_w("one", 0.0, 0.2, "A"), _w("and", 0.2, 0.3, "A"), _w("two", 0.3, 0.5, "A")]
        res = wder_decomposed(ref, hyp)
        assert res.insertions == 1
        assert res.asr_component == pytest.approx(0.5)


class TestWDERAssignment:
    def test_correct_words_wrong_speaker(self):
        ref = [
            _w("hello", 0.0, 0.4, "S1"),
            _w("world", 0.4, 0.8, "S2"),
        ]
        hyp = [
            _w("hello", 0.0, 0.4, "A"),
            _w("world", 0.4, 0.8, "A"),  # same cluster instead of two
        ]
        res = wder_decomposed(ref, hyp)
        assert res.asr_component == 0.0
        assert res.assignment_component == pytest.approx(0.5)

    def test_permutation_finds_best_mapping(self):
        ref = [_w("a", 0.0, 0.1, "S1"), _w("b", 0.1, 0.2, "S2")]
        # Hyp swaps labels — relabeling must normalize to zero.
        hyp = [_w("a", 0.0, 0.1, "Speaker 2"), _w("b", 0.1, 0.2, "Speaker 1")]
        res = wder_decomposed(ref, hyp)
        assert res.assignment_component == 0.0

    def test_total_is_additive(self):
        ref = [
            _w("alpha", 0.0, 0.1, "S1"),
            _w("beta", 0.1, 0.2, "S2"),
            _w("gamma", 0.2, 0.3, "S2"),
        ]
        hyp = [
            _w("alpha", 0.0, 0.1, "A"),  # correct word, correct mapping A→S1
            _w("beta", 0.1, 0.2, "A"),   # correct word, WRONG mapping (B would be S2)
            _w("delta", 0.2, 0.3, "B"),  # substitution
        ]
        res = wder_decomposed(ref, hyp)
        assert res.substitutions == 1
        assert res.asr_component == pytest.approx(1 / 3)
        # one correctly-recognized word with wrong speaker → 1/3 assignment
        assert res.assignment_component == pytest.approx(1 / 3)
        assert res.total == pytest.approx(res.asr_component + res.assignment_component)


class TestWDEREdges:
    def test_empty_ref_returns_zero(self):
        res = wder_decomposed([], [_w("x", 0, 0.1, "A")])
        assert res.total == 0.0
        assert res.n_ref == 0

    def test_empty_hyp_is_all_deletions(self):
        ref = [_w("a", 0, 0.1, "S1"), _w("b", 0.1, 0.2, "S1")]
        res = wder_decomposed(ref, [])
        assert res.deletions == 2
        assert res.asr_component == 1.0


# ---------------------------------------------------------------------------
# cpWER
# ---------------------------------------------------------------------------

class TestCPWER:
    def test_identical_returns_zero(self):
        ref = {"S1": "hello world", "S2": "good morning"}
        hyp = {"A": "hello world", "B": "good morning"}
        assert cpwer(ref, hyp) == 0.0

    def test_swapped_speaker_labels_still_zero(self):
        ref = {"S1": "hello world", "S2": "good morning"}
        hyp = {"A": "good morning", "B": "hello world"}
        assert cpwer(ref, hyp) == 0.0

    def test_word_error_counted(self):
        ref = {"S1": "hello world"}
        hyp = {"A": "hello word"}  # 1 substitution out of 2 ref tokens
        assert cpwer(ref, hyp) == pytest.approx(0.5)

    def test_accepts_word_sequences(self):
        ref_words = [_w("hello", 0, 0.1, "S1"), _w("world", 0.1, 0.2, "S1")]
        hyp_words = [_w("hello", 0, 0.1, "A"), _w("world", 0.1, 0.2, "A")]
        assert cpwer(ref_words, hyp_words) == 0.0

    def test_missing_hyp_speaker_scored_as_deletion(self):
        ref = {"S1": "hello", "S2": "world"}
        hyp = {"A": "hello"}
        # 1 error (missing "world") over 2 ref tokens
        assert cpwer(ref, hyp) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# speaker_purity
# ---------------------------------------------------------------------------

class TestSpeakerPurity:
    def test_perfect_single_speaker(self):
        ref = [Turn(0.0, 10.0, "S1")]
        hyp = [Turn(0.0, 10.0, "A")]
        assert speaker_purity(ref, hyp) == pytest.approx(1.0)

    def test_mixed_cluster_is_impure(self):
        # Cluster A spans both reference speakers 50/50.
        ref = [Turn(0.0, 5.0, "S1"), Turn(5.0, 10.0, "S2")]
        hyp = [Turn(0.0, 10.0, "A")]
        assert speaker_purity(ref, hyp) == pytest.approx(0.5)

    def test_empty_hyp_returns_zero(self):
        assert speaker_purity([Turn(0.0, 1.0, "S1")], []) == 0.0


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

class TestLoaders:
    def test_load_hyp_derives_turns(self, tmp_path):
        path = tmp_path / "clip.whisper.json"
        path.write_text(json.dumps({
            "words": [
                {"start": 0.0, "end": 0.4, "word": "hello", "speaker": "Speaker 1"},
                {"start": 0.4, "end": 0.8, "word": "there", "speaker": "Speaker 1"},
                {"start": 0.9, "end": 1.2, "word": "hi", "speaker": "Speaker 2"},
            ],
            "text": "hello there hi",
        }), encoding="utf-8")

        hyp = load_hyp_from_whisper_json(path)
        assert len(hyp.words) == 3
        assert [t.speaker for t in hyp.turns] == ["Speaker 1", "Speaker 2"]
        assert hyp.turns[0].end == pytest.approx(0.8)

    def test_load_hyp_uses_explicit_turns_when_present(self, tmp_path):
        path = tmp_path / "clip.whisper.json"
        path.write_text(json.dumps({
            "words": [{"start": 0.0, "end": 0.4, "word": "hi", "speaker": "S1"}],
            "turns": [{"start": 0.0, "end": 0.4, "speaker": "S1"}],
        }), encoding="utf-8")
        hyp = load_hyp_from_whisper_json(path)
        assert len(hyp.turns) == 1

    def test_load_ref(self, tmp_path):
        path = tmp_path / "clip.ref.json"
        path.write_text(json.dumps({
            "version": 2,
            "reference_text": "hello there",
            "reference_speakers": ["S1"],
            "words": [
                {"start": 0.0, "end": 0.4, "word": "hello", "speaker": "S1"},
                {"start": 0.4, "end": 0.8, "word": "there", "speaker": "S1"},
            ],
            "turns": [{"start": 0.0, "end": 0.8, "speaker": "S1"}],
        }), encoding="utf-8")
        ref = load_ref_from_json(path)
        assert ref.reference_text == "hello there"
        assert len(ref.words) == 2


# ---------------------------------------------------------------------------
# DER (pyannote.metrics optional)
# ---------------------------------------------------------------------------

class TestDER:
    def test_der_raises_when_pyannote_metrics_missing(self):
        try:
            import pyannote.metrics  # noqa: F401
        except ImportError:
            from core.diar_metrics import der
            with pytest.raises(RuntimeError):
                der([Turn(0, 1, "S1")], [Turn(0, 1, "A")])
            return
        pytest.skip("pyannote.metrics installed; covered in integration tests")

    @pytest.mark.integration
    def test_der_perfect_is_zero(self):
        pytest.importorskip("pyannote.metrics")
        from core.diar_metrics import der
        ref = [Turn(0.0, 5.0, "S1"), Turn(5.0, 10.0, "S2")]
        hyp = [Turn(0.0, 5.0, "A"), Turn(5.0, 10.0, "B")]
        assert der(ref, hyp, collar=0.0) == pytest.approx(0.0, abs=1e-6)
