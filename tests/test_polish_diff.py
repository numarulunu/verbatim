"""
Phase 4 tests for persons/polish_diff.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import persons.polish_diff as _pd
from persons.polish_diff import _ascii_fold_ro, _phonetic_keys_match, apply_patches


@pytest.fixture(autouse=True)
def _enable_phonetic_gate(monkeypatch):
    """The polish_diff phonetic gate is keyed off config.PHONETIC_DISTANCE_GATE,
    which defaults to None (Phase 1 not committed). Tests need it active."""
    monkeypatch.setattr(_pd, "PHONETIC_DISTANCE_GATE", "metaphone_ro_fold")


# --------------------------------------------------------------------------- #
# Romanian ASCII fold + phonetic gate
# --------------------------------------------------------------------------- #

def test_ascii_fold_strips_all_ro_diacritics() -> None:
    s = "Ăă Ââ Îî Șș Țț ŞşŢţ"
    assert _ascii_fold_ro(s) == "Aa Aa Ii Ss Tt SsTt"


def test_phonetic_keys_match_treats_diacritic_variants_as_same_word() -> None:
    """Romanian inflection 'inimă' / 'inima' is the canonical case the
    phonetic gate must accept (both → same Metaphone key after RO fold)."""
    assert _phonetic_keys_match("inimă", "inima")


def test_phonetic_keys_match_rejects_actually_different_words() -> None:
    """Same-length, similar-looking words with different sounds must not
    pass the gate. 'mare' (sea) vs 'pare' (seems) → distinct Metaphone keys."""
    assert not _phonetic_keys_match("mare", "pare")


def test_phonetic_keys_match_handles_empty_input() -> None:
    assert not _phonetic_keys_match("", "anything")
    assert not _phonetic_keys_match("anything", "")


# --------------------------------------------------------------------------- #
# apply_patches gates
# --------------------------------------------------------------------------- #

def _segment(text: str, words: list[dict]) -> dict:
    return {"start": 0.0, "end": 1.0, "text": text, "words": words}


def _word(s: str, prob: float = 0.4) -> dict:
    return {"start": 0.0, "end": 0.4, "word": s, "probability": prob}


def test_accepts_phonetic_match_below_confidence_threshold() -> None:
    """Low-confidence word with phonetic-matching proposal → accepted."""
    seg = _segment("inima", [_word("inima", 0.3)])
    patches = [{
        "segment_index": 0, "word_index": 0,
        "original": "inima", "proposed": "inimă",
        "rationale": "diacritic restore", "confidence": 0.9,
    }]
    out, rejected = apply_patches([seg], patches, threshold=0.6)
    assert rejected == []
    assert out[0]["words"][0]["word"] == "inimă"
    assert out[0]["text"] == "inimă"


def test_rejects_high_confidence_word() -> None:
    """If Whisper was already >= threshold confident, polish must not touch it."""
    seg = _segment("hello", [_word("hello", 0.95)])
    patches = [{
        "segment_index": 0, "word_index": 0,
        "original": "hello", "proposed": "helo",
        "rationale": "typo", "confidence": 0.9,
    }]
    out, rejected = apply_patches([seg], patches, threshold=0.6)
    assert len(rejected) == 1
    assert rejected[0]["rejection_reason"] == "word_confidence_above_threshold"
    assert out[0]["text"] == "hello"


def test_rejects_phonetically_dissimilar_swap() -> None:
    """LLM tries to swap 'mare' for 'pare' — different Metaphone keys → reject."""
    seg = _segment("mare", [_word("mare", 0.3)])
    patches = [{
        "segment_index": 0, "word_index": 0,
        "original": "mare", "proposed": "pare",
        "rationale": "context fit", "confidence": 0.85,
    }]
    out, rejected = apply_patches([seg], patches, threshold=0.6)
    assert len(rejected) == 1
    assert rejected[0]["rejection_reason"] == "phonetic_keys_differ"


def test_accepts_glossary_corroborated_swap_regardless_of_phonetics() -> None:
    """A swap that doesn't match phonetics but IS in the lesson glossary is
    accepted — the glossary is a domain authority that overrides the gate."""
    seg = _segment("apojio", [_word("apojio", 0.4)])
    patches = [{
        "segment_index": 0, "word_index": 0,
        "original": "apojio", "proposed": "appoggio",
        "rationale": "glossary canonical form", "confidence": 0.9,
    }]
    out, rejected = apply_patches([seg], patches, glossary={"appoggio"}, threshold=0.6)
    assert rejected == []
    assert out[0]["words"][0]["word"] == "appoggio"


def test_rejects_invalid_segment_index() -> None:
    seg = _segment("x", [_word("x", 0.4)])
    patches = [{
        "segment_index": 5, "word_index": 0,
        "original": "x", "proposed": "y", "rationale": "?", "confidence": 1.0,
    }]
    out, rejected = apply_patches([seg], patches, threshold=0.6)
    assert rejected[0]["rejection_reason"] == "invalid_segment_index"


def test_rejects_original_mismatch() -> None:
    """Patch claims original='X' but the actual word is 'Y' → reject (LLM
    may have mis-counted indices)."""
    seg = _segment("y", [_word("y", 0.3)])
    patches = [{
        "segment_index": 0, "word_index": 0,
        "original": "x", "proposed": "z",
        "rationale": "?", "confidence": 0.9,
    }]
    out, rejected = apply_patches([seg], patches, threshold=0.6)
    assert rejected[0]["rejection_reason"] == "original_mismatch"


def test_records_audit_trail_on_accepted_patch() -> None:
    seg = _segment("inima", [_word("inima", 0.3)])
    patches = [{
        "segment_index": 0, "word_index": 0,
        "original": "inima", "proposed": "inimă",
        "rationale": "diacritic restore", "confidence": 0.9,
    }]
    out, _ = apply_patches([seg], patches, threshold=0.6)
    trail = out[0]["polish_patches_applied"]
    assert len(trail) == 1
    assert trail[0]["from"] == "inima"
    assert trail[0]["to"] == "inimă"
    assert trail[0]["rationale"] == "diacritic restore"


def test_no_change_patches_are_rejected_silently() -> None:
    seg = _segment("a", [_word("a", 0.3)])
    patches = [{
        "segment_index": 0, "word_index": 0,
        "original": "a", "proposed": "a",
        "rationale": "no-op", "confidence": 1.0,
    }]
    out, rejected = apply_patches([seg], patches, threshold=0.6)
    assert rejected[0]["rejection_reason"] == "no_change"
