"""
First 3 sessions of any new person must require real match confidence > 0.75
or the voice-library update must be rejected (brief §7 + SMAC Finding #6).
Bootstrap session 1 gets a free pass (confidence=1.0 by construction, the
cluster IS this person). Sessions 2 and 3 must check real confidence.
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


def test_register_new_sets_bootstrap_sessions_remaining_to_3(tmp_project):
    import config  # noqa: F401
    from persons import registry

    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    assert person.bootstrap_sessions_remaining == 3


def test_session_2_with_low_confidence_rejected(tmp_project, monkeypatch):
    """After bootstrap, session 2 with real confidence < 0.75 must NOT
    decrement the trust counter or update the voice library."""
    _reset()
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import update_voice_libraries

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    # Simulate that bootstrap session 1 already happened.
    person.bootstrap_sessions_remaining = 2
    person.n_sessions_as_teacher = 1
    registry.save(person)

    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("x.mp4"),
    )
    audio = np.ones(16000 * 30, dtype=np.float32)
    # Session 2: low confidence (0.5 < 0.75 gate)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 0.5,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    update_voice_libraries(segments, label_to_person, audio, 16000, meta)

    after = registry.load("vasquez")
    assert after.bootstrap_sessions_remaining == 2, "counter must NOT decrement on rejected update"
    assert after.n_sessions_as_teacher == 1, "session count must NOT increment on rejected update"


def test_session_2_with_high_confidence_decrements_counter(tmp_project, monkeypatch):
    _reset()
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import update_voice_libraries

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    person.bootstrap_sessions_remaining = 2
    person.n_sessions_as_teacher = 1
    # Seed the speaking.npy so the update finds a prior centroid.
    pdir = tmp_project / "_voiceprints" / "people" / "vasquez"
    pdir.mkdir(parents=True, exist_ok=True)
    seed = np.random.RandomState(0).randn(512).astype(np.float32)
    seed = seed / np.linalg.norm(seed)
    np.save(pdir / "speaking.npy", seed)
    person.region_session_counts = {"speaking": 1}
    person.observed_regions = ["speaking"]
    registry.save(person)

    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("x.mp4"),
    )
    audio = np.ones(16000 * 30, dtype=np.float32)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 0.9,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    update_voice_libraries(segments, label_to_person, audio, 16000, meta)

    after = registry.load("vasquez")
    assert after.bootstrap_sessions_remaining == 1
    assert after.n_sessions_as_teacher == 2


def test_silent_noop_does_not_decrement_counter(tmp_project, monkeypatch):
    """When audio is too short for any region to meet VOICE_LIB_MIN_REGION_SECONDS,
    `_update_one_person` silently no-ops. The bootstrap trust counter must NOT
    decrement — otherwise a person accumulates empty sessions and graduates
    the gate without any real voice data collected."""
    _reset()
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import update_voice_libraries

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    person.bootstrap_sessions_remaining = 2
    person.n_sessions_as_teacher = 1
    # Seed speaking.npy so the 0.75 gate path wouldn't auto-reject
    # (we want to exercise the post-gate silent-noop path specifically).
    pdir = tmp_project / "_voiceprints" / "people" / "vasquez"
    pdir.mkdir(parents=True, exist_ok=True)
    seed = np.random.RandomState(0).randn(512).astype(np.float32)
    seed = seed / np.linalg.norm(seed)
    np.save(pdir / "speaking.npy", seed)
    person.region_session_counts = {"speaking": 1}
    person.observed_regions = ["speaking"]
    registry.save(person)

    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("x.mp4"),
    )
    # Audio too short for VOICE_LIB_MIN_REGION_SECONDS (10s) — only 5s.
    audio = np.ones(16000 * 5, dtype=np.float32)
    segments = [{
        "start": 0.0, "end": 5.0,   # 5s < 10s threshold
        "speaker_id": "vasquez", "speaker_confidence": 0.9,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    update_voice_libraries(segments, label_to_person, audio, 16000, meta)

    after = registry.load("vasquez")
    assert after.bootstrap_sessions_remaining == 2, (
        "counter must NOT decrement when _update_one_person silently no-ops "
        "(no region met VOICE_LIB_MIN_REGION_SECONDS)"
    )
