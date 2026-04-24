"""
polish_diff — Phase 4 patch-application logic for the diff-schema polish.

The 2026-04-24 plan replaces the current "LLM rewrites the segment text"
flow with "LLM emits a list of patches". A patch is a structured
recommendation:

    {
      "segment_index": int,    # which segment in the chunk
      "word_index":    int,    # which word inside that segment's words[]
      "original":      str,    # what's there now
      "proposed":      str,    # what the LLM wants to substitute
      "rationale":     str,    # the LLM's stated reason
      "confidence":    float,  # 0..1, the LLM's self-rated confidence
    }

This module receives a chunk of segments + the LLM's proposed patches and
applies only the patches that pass the deterministic gate:

  1. Sanity: original word actually exists at (segment_index, word_index).
  2. Word-confidence: original word's per-word probability < threshold
     (no point rewriting words Whisper was already sure about).
  3. Phonetic-distance: jellyfish.metaphone(ascii_fold(original)) ==
     jellyfish.metaphone(ascii_fold(proposed))  OR  proposed in glossary.
     Romanian inflection makes raw Levenshtein too blunt — phonetic
     similarity is a better proxy for "this is the same word, fixed".

Rejected patches are logged to `rejected` so the renderer review queue can
surface what the LLM tried but couldn't justify.

NOTE: This module is independent of the prompt template + chunk loop. The
existing free-rewrite path in polish_engine.py is untouched. Switching the
pipeline to diff-schema requires:
  1. New prompt that asks for patches (a follow-up after live Claude testing).
  2. _extract_json validator extended to accept the patch shape.
  3. polish_chunk_cli/api consumers calling apply_patches before merge.
"""
from __future__ import annotations

import logging
from typing import Any

from config import (
    PHONETIC_DISTANCE_GATE,
    WORD_CONFIDENCE_THRESHOLD,
)

log = logging.getLogger(__name__)


# Romanian diacritic ASCII-fold for Metaphone. The Metaphone implementation
# in jellyfish was designed for English phonemes; folding diacritics first
# ensures words like "inimă" / "inima" map to the same phonetic key.
_RO_FOLD_TABLE = str.maketrans({
    "ă": "a", "Ă": "A",
    "â": "a", "Â": "A",
    "î": "i", "Î": "I",
    "ș": "s", "Ș": "S",
    "ş": "s", "Ş": "S",  # legacy cedilla form
    "ț": "t", "Ț": "T",
    "ţ": "t", "Ţ": "T",  # legacy cedilla form
})


def _ascii_fold_ro(s: str) -> str:
    return (s or "").translate(_RO_FOLD_TABLE)


def _phonetic_keys_match(a: str, b: str) -> bool:
    """Two strings have the same Metaphone key after RO ASCII-fold."""
    if not a or not b:
        return False
    import jellyfish
    key_a = jellyfish.metaphone(_ascii_fold_ro(a).lower())
    key_b = jellyfish.metaphone(_ascii_fold_ro(b).lower())
    return key_a == key_b and key_a != ""


def _word_confidence(seg: dict, word_index: int) -> float | None:
    """Return per-word probability for a given segment's word, or None."""
    words = seg.get("words")
    if not words or word_index >= len(words):
        return None
    return words[word_index].get("probability")


def _apply_one_patch(
    segments: list[dict],
    patch: dict,
    glossary: set[str],
    threshold: float,
) -> tuple[bool, str | None]:
    """Try to apply one patch. Returns (accepted, rejection_reason).

    Mutates segments in place when accepted.
    """
    seg_i = patch.get("segment_index")
    word_i = patch.get("word_index")
    original = (patch.get("original") or "").strip()
    proposed = (patch.get("proposed") or "").strip()

    if not isinstance(seg_i, int) or seg_i < 0 or seg_i >= len(segments):
        return False, "invalid_segment_index"
    if not isinstance(word_i, int) or word_i < 0:
        return False, "invalid_word_index"
    if not original or not proposed:
        return False, "empty_text"
    if original == proposed:
        return False, "no_change"

    seg = segments[seg_i]
    words = seg.get("words")
    if not words or word_i >= len(words):
        return False, "missing_word_metadata"

    actual_word = (words[word_i].get("word") or "").strip()
    # Defensive comparison after stripping LSP whitespace from faster-whisper.
    if actual_word.lstrip() != original.lstrip():
        return False, "original_mismatch"

    confidence = _word_confidence(seg, word_i)
    if confidence is None:
        # Without per-word probability we can't gate. Allow only
        # glossary-corroborated patches when this metadata is missing.
        if proposed.lower() not in glossary:
            return False, "no_word_confidence_and_not_glossary"
    elif confidence >= threshold:
        return False, "word_confidence_above_threshold"

    if proposed.lower() not in glossary:
        if PHONETIC_DISTANCE_GATE != "metaphone_ro_fold":
            # Reserved for future gate algorithms; no other implementation yet.
            return False, "unknown_phonetic_gate"
        if not _phonetic_keys_match(original, proposed):
            return False, "phonetic_keys_differ"

    # Accept: rewrite the word in-place AND rebuild the segment text from
    # the (now-updated) word list so downstream consumers stay coherent.
    words[word_i]["word"] = proposed
    seg["text"] = " ".join(w.get("word", "").strip() for w in words).strip()
    seg.setdefault("polish_patches_applied", []).append({
        "word_index": word_i,
        "from": original,
        "to": proposed,
        "rationale": patch.get("rationale"),
    })
    return True, None


def apply_patches(
    segments: list[dict],
    patches: list[dict],
    glossary: set[str] | None = None,
    threshold: float | None = None,
) -> tuple[list[dict], list[dict]]:
    """Apply each patch through the gate. Returns (segments, rejected_patches).

    `segments` is mutated in place; the returned reference is the same list.
    `rejected_patches` carries each rejection reason for the review-queue UI.
    """
    if threshold is None:
        threshold = WORD_CONFIDENCE_THRESHOLD if WORD_CONFIDENCE_THRESHOLD is not None else 0.6
    glossary = {g.lower() for g in (glossary or set())}

    rejected: list[dict] = []
    for patch in patches:
        accepted, reason = _apply_one_patch(segments, patch, glossary, threshold)
        if not accepted:
            rejected.append({**patch, "rejection_reason": reason})

    return segments, rejected
