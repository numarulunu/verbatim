"""
When a person appears in a session but has no region with at least
VOICE_LIB_MIN_REGION_SECONDS of audio, _update_one_person must NOT
increment session counters or write a stale universal — otherwise the
first-3-sessions gate counts empty appearances against the person.
"""
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    monkeypatch.setenv("VERBATIM_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "config" or mod.startswith("persons") or mod.startswith("stage3"):
            sys.modules.pop(mod, None)
    yield tmp_path


_embed_calls = 0


def _fake_embed(audio):
    global _embed_calls
    _embed_calls += 1
    rng = np.random.RandomState(_embed_calls)
    vec = rng.randn(512).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-9)


def _reset():
    global _embed_calls
    _embed_calls = 0


def test_empty_region_clips_does_not_increment_counters(tmp_project, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.WARNING)
    _reset()
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import _update_one_person

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)

    person = registry.register_new(
        id_="alessandro", display_name="alessandro",
        default_role="teacher", first_seen="2025-08-07",
    )
    baseline_n_teacher = person.n_sessions_as_teacher
    baseline_total_hours = person.total_hours

    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="alessandro", student_id="ionut",
        source_path=Path("x.mp4"),
    )

    # All clips are under VOICE_LIB_MIN_REGION_SECONDS (5s only).
    region_clips = {"speaking": [np.zeros(16000 * 5, dtype=np.float32)]}

    result = _update_one_person(person, region_clips, total_duration_s=5.0, meta=meta, is_redo=False)

    after = registry.load("alessandro")
    assert result is False, "must signal no-update to caller"
    assert after.n_sessions_as_teacher == baseline_n_teacher, "no update happened — count must not increment"
    assert after.total_hours == baseline_total_hours
    # Must have logged a visible warning (not silent).
    assert any("empty" in rec.message.lower() or "insufficient" in rec.message.lower() or "skipped" in rec.message.lower() or "no region" in rec.message.lower()
               for rec in caplog.records), "silent skip — add a warning"


def test_has_region_clips_does_increment(tmp_project, monkeypatch):
    """Baseline: when region_clips does contain enough audio, counters DO increment."""
    _reset()
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import _update_one_person

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)

    person = registry.register_new(
        id_="alessandro", display_name="alessandro",
        default_role="teacher", first_seen="2025-08-07",
    )
    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="alessandro", student_id="ionut",
        source_path=Path("x.mp4"),
    )

    region_clips = {"speaking": [np.zeros(16000 * 30, dtype=np.float32)]}  # 30s
    result = _update_one_person(person, region_clips, total_duration_s=30.0, meta=meta, is_redo=False)

    after = registry.load("alessandro")
    assert result is True
    assert after.n_sessions_as_teacher == 1
