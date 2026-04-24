"""
Phase 4 tests for persons/polish_ner_audit.py.

spaCy may not be installed in CI — the auditor must degrade to a permissive
no-op rather than crash. These tests verify that contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from persons.polish_ner_audit import (
    _NLP_CACHE,
    audit_segment_pair,
    find_introduced_entities,
)


def setup_function() -> None:
    _NLP_CACHE.clear()


def test_degrades_to_permissive_when_spacy_missing(monkeypatch) -> None:
    """No spaCy installed → audit returns empty introduced-set."""
    # Force the import-error branch even if spaCy is installed in dev.
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "spacy":
            raise ImportError("simulated missing spacy")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _mock_import)
    intro = find_introduced_entities("hello world", "hello world bach", language="en")
    assert intro == set()


def test_degrades_when_model_for_language_missing(monkeypatch) -> None:
    """Unknown language code → audit no-ops cleanly."""
    intro = find_introduced_entities("text", "text", language="xx")
    assert intro == set()


def test_audit_segment_pair_accepts_when_audit_disabled() -> None:
    """When the auditor degrades, every patch is accepted (permissive)."""
    accepted, intro = audit_segment_pair(
        {"text": "hello"},
        {"text": "hello someone NEW"},
        language="xx",  # unknown → audit disabled
    )
    assert accepted is True
    assert intro == set()


def test_caches_nlp_per_language(monkeypatch) -> None:
    """A second call for the same language must not re-attempt the import.
    We assert the cache is populated after a single call (with None or model)."""
    find_introduced_entities("a", "b", language="xx")
    assert "xx" in _NLP_CACHE
    assert _NLP_CACHE["xx"] is None  # unsupported → None
