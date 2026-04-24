"""
polish_ner_audit — Phase 4 named-entity diff between original and polished.

Constraint: an LLM polish step must NEVER introduce a named entity (person
name, organization, location, work title) that wasn't already in the
original ASR output. Hallucinated proper nouns are the highest-risk
correction class for vocal-lesson transcripts (student names, repertoire
titles, composer attributions).

This module runs spaCy NER over both the pre- and post-patch text of each
segment and rejects patches that introduce a new entity. The check is
defensive: spaCy may be absent in some environments — the auditor degrades
to a permissive no-op and logs a warning, never crashes the pipeline.

The Romanian model `ro_core_news_sm` is the smallest practical option;
download separately:
    pip install spacy
    python -m spacy download ro_core_news_sm

Exposed contract:
    audit_patches(segments_before, segments_after, language) -> list[dict]
        Returns a list of accepted patches' segment indices to rollback.
        (Empty when spaCy unavailable.)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


_NLP_CACHE: dict[str, object] = {}
# spaCy model names per language. Add more as the corpus expands.
_MODEL_FOR_LANGUAGE = {
    "ro": "ro_core_news_sm",
    "en": "en_core_web_sm",
}
# Entity labels we treat as "must not be introduced". We deliberately exclude
# CARDINAL/ORDINAL/MONEY/PERCENT — Whisper often spells out numbers that
# polish converts to digits and vice-versa; that's not a hallucination.
_ENTITY_LABELS = {"PERSON", "ORG", "GPE", "LOC", "WORK_OF_ART", "EVENT", "PRODUCT"}


def _load_nlp(language: str):
    if language in _NLP_CACHE:
        return _NLP_CACHE[language]
    try:
        import spacy
    except ImportError:
        log.warning("spacy not installed; NER audit disabled (install: pip install spacy)")
        _NLP_CACHE[language] = None
        return None
    model_name = _MODEL_FOR_LANGUAGE.get(language)
    if not model_name:
        log.warning("no spaCy model registered for language=%r; NER audit skipped", language)
        _NLP_CACHE[language] = None
        return None
    try:
        nlp = spacy.load(model_name, disable=["parser", "tagger", "lemmatizer"])
    except OSError:
        log.warning(
            "spaCy model %r missing; NER audit disabled (install: python -m spacy download %s)",
            model_name, model_name,
        )
        _NLP_CACHE[language] = None
        return None
    _NLP_CACHE[language] = nlp
    return nlp


def _entities(text: str, nlp) -> set[tuple[str, str]]:
    """Returns {(entity_text_lower, entity_label)} for the input string."""
    if not text or nlp is None:
        return set()
    doc = nlp(text)
    return {(ent.text.lower(), ent.label_) for ent in doc.ents if ent.label_ in _ENTITY_LABELS}


def find_introduced_entities(
    original_text: str,
    polished_text: str,
    language: str,
) -> set[tuple[str, str]]:
    """Returns the set of (entity_text, label) that appear in polished_text
    but not in original_text. Empty set when spaCy is unavailable."""
    nlp = _load_nlp(language)
    if nlp is None:
        return set()
    return _entities(polished_text, nlp) - _entities(original_text, nlp)


def audit_segment_pair(
    original: dict,
    polished: dict,
    language: str,
) -> tuple[bool, set[tuple[str, str]]]:
    """Returns (accepted, introduced_entities). accepted=False when the
    polished text introduces any entity that wasn't in the original."""
    intro = find_introduced_entities(
        original.get("text", ""), polished.get("text", ""), language,
    )
    return (len(intro) == 0, intro)
