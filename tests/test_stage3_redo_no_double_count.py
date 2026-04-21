"""
Redo must not double-count sessions or re-blend audio.

Simulated scenario: process a person once (is_redo=False), then process the
same session again (is_redo=True). After the redo, neither the centroid nor
session counts should have changed relative to the first-pass result.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest


@pytest.fixture
def tmp_voiceprint_root(monkeypatch, tmp_path):
    monkeypatch.setenv("VOCALITY_ROOT", str(tmp_path))
    # Force the config module to re-evaluate PROJECT_ROOT and propagate to all
    # modules that bound VOICEPRINT_DIR / PROJECT_ROOT at import time.
    for mod in list(sys.modules):
        if mod in ("config",) or mod.startswith("persons") or mod.startswith("stage3"):
            sys.modules.pop(mod, None)
    yield tmp_path


_embed_calls = 0


def _fake_embed(audio):
    """Call-count-sensitive fake: each invocation returns a different vector.

    Seeding by audio content can collide (e.g., len % 10000 == 0 for same-size
    clips), making a re-blend produce the same result as no-blend and hiding
    regressions in the is_redo guard.
    """
    global _embed_calls
    _embed_calls += 1
    rng = np.random.RandomState(_embed_calls)
    vec = rng.randn(512).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-9)


def _reset_embed_counter():
    global _embed_calls
    _embed_calls = 0


def test_redo_does_not_double_count(tmp_voiceprint_root, monkeypatch):
    """Running update_voice_libraries twice with is_redo=True the second time
    must leave centroid + session counters as they were after first pass."""
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry, schema
    from stage3_postprocess import update_voice_libraries

    _reset_embed_counter()
    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    meta = SessionMeta(
        date="2025-08-07", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("test.mp4"),
    )

    # Pre-register vasquez so identify_speakers isn't exercised in this test.
    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen=meta.date,
    )

    # Build a single 20s (>VOICE_LIB_MIN_REGION_SECONDS) segment attributed to vasquez.
    audio = np.ones(16000 * 30, dtype=np.float32)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 1.0,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    # First pass (normal).
    update_voice_libraries(segments, label_to_person, audio, 16000, meta, is_redo=False)
    rec1 = registry.load("vasquez")
    centroid1 = np.load(
        tmp_voiceprint_root / "_voiceprints" / "people" / "vasquez" / "speaking.npy"
    )

    # Redo pass — same inputs, is_redo=True.
    update_voice_libraries(segments, label_to_person, audio, 16000, meta, is_redo=True)
    rec2 = registry.load("vasquez")
    centroid2 = np.load(
        tmp_voiceprint_root / "_voiceprints" / "people" / "vasquez" / "speaking.npy"
    )

    # Session counts unchanged.
    assert rec1.n_sessions_as_teacher == rec2.n_sessions_as_teacher == 1
    assert rec1.region_session_counts == rec2.region_session_counts

    # Centroid unchanged.
    assert np.allclose(centroid1, centroid2), "redo must not re-blend the same audio"


def test_redo_flag_defaults_to_false(tmp_voiceprint_root, monkeypatch):
    """Existing callers that don't pass is_redo must still default to the
    normal-run behavior (update applied)."""
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import update_voice_libraries

    _reset_embed_counter()
    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    meta = SessionMeta(
        date="2025-08-07", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("test.mp4"),
    )
    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen=meta.date,
    )
    audio = np.ones(16000 * 30, dtype=np.float32)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 1.0,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    # Call without is_redo — must behave as is_redo=False.
    update_voice_libraries(segments, label_to_person, audio, 16000, meta)
    assert registry.load("vasquez").n_sessions_as_teacher == 1


def test_redo_skips_region_when_no_prior_file_exists(tmp_voiceprint_root, monkeypatch):
    """If a region's .npy was never saved (e.g., first pass crashed), a redo
    with is_redo=True must SKIP that region entirely — not write a universal
    centroid derived from a region with no corresponding .npy or
    region_session_counts entry."""
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import update_voice_libraries

    _reset_embed_counter()
    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    meta = SessionMeta(
        date="2025-08-07", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("test.mp4"),
    )
    # Register vasquez but don't save any region centroids.
    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen=meta.date,
    )
    # Don't pre-save speaking.npy.

    audio = np.ones(16000 * 30, dtype=np.float32)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 1.0,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    update_voice_libraries(segments, label_to_person, audio, 16000, meta, is_redo=True)

    pdir = tmp_voiceprint_root / "_voiceprints" / "people" / "vasquez"
    assert not (pdir / "speaking.npy").exists(), (
        "redo must NOT create speaking.npy when it didn't already exist"
    )
    assert not (pdir / "universal.npy").exists(), (
        "redo must NOT create universal.npy derived from a ghost region"
    )
