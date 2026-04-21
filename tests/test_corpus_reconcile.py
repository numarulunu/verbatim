"""
reconcile_from_polished scans POLISHED_DIR for transcripts missing from
corpus.json and replays them. Protects against a crash between the
polished-JSON write and the corpus-update in stage3.finalize.
"""
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    monkeypatch.setenv("VOCALITY_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "config" or mod.startswith("persons"):
            sys.modules.pop(mod, None)
    yield tmp_path


def _mk_polished(dir_path: Path, file_id: str, language: str, duration_s: float,
                 teacher: str, student: str) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{file_id}.json").write_text(
        json.dumps({
            "file_id": file_id,
            "date": file_id.split("_")[0],
            "language": language,
            "duration_s": duration_s,
            "processed_at": "2026-04-21T00:00:00+00:00",
            "pipeline_version": "1.0.0",
            "polish_engine": "cli",
            "overlap_ratio": 0.0,
            "source_codec": "aac",
            "source_bitrate": 128000,
            "mfa_aligned": False,
            "participants": [
                {"id": teacher, "name": teacher, "role": "teacher"},
                {"id": student, "name": student, "role": "student"},
            ],
            "segments": [{"start": 0.0, "end": 1.0, "text": "hi"}],
            "processed_at_db_state": {},
        }, indent=2),
        encoding="utf-8",
    )


def test_reconcile_finds_orphan_polished(tmp_project):
    import config
    from persons import corpus

    _mk_polished(config.POLISHED_DIR, "2025-08-07_vasquez__ionut_en",
                 "en", 600.0, "vasquez", "ionut")

    # corpus.json doesn't exist yet → reconciler should create it with the
    # orphan transcript.
    added = corpus.reconcile_from_polished()

    assert added == 1
    entries = corpus.load()
    assert len(entries) == 1
    assert entries[0]["file_id"] == "2025-08-07_vasquez__ionut_en"
    assert entries[0]["teacher_id"] == "vasquez"
    assert entries[0]["student_id"] == "ionut"


def test_reconcile_skips_already_indexed(tmp_project):
    import config
    from persons import corpus

    _mk_polished(config.POLISHED_DIR, "2025-08-07_vasquez__ionut_en",
                 "en", 600.0, "vasquez", "ionut")

    first = corpus.reconcile_from_polished()
    second = corpus.reconcile_from_polished()

    assert first == 1
    assert second == 0, "second run must be a no-op"
    assert len(corpus.load()) == 1


def test_reconcile_adds_only_missing(tmp_project):
    import config
    from persons import corpus

    _mk_polished(config.POLISHED_DIR, "2025-08-07_vasquez__ionut_en",
                 "en", 600.0, "vasquez", "ionut")
    _mk_polished(config.POLISHED_DIR, "2025-10-06_ionut__luiza_en",
                 "en", 300.0, "ionut", "luiza")

    # Pre-populate corpus with only one entry.
    corpus.append_session({"file_id": "2025-08-07_vasquez__ionut_en",
                            "date": "2025-08-07", "language": "en",
                            "teacher_id": "vasquez", "student_id": "ionut"})

    added = corpus.reconcile_from_polished()
    assert added == 1, "only the luiza entry is missing"
    file_ids = [e["file_id"] for e in corpus.load()]
    assert sorted(file_ids) == [
        "2025-08-07_vasquez__ionut_en",
        "2025-10-06_ionut__luiza_en",
    ]


def test_reconcile_skips_corrupt_json(tmp_project, caplog):
    import logging
    caplog.set_level(logging.WARNING)
    import config
    from persons import corpus

    # One valid polished + one corrupt file.
    _mk_polished(config.POLISHED_DIR, "2025-08-07_vasquez__ionut_en",
                 "en", 600.0, "vasquez", "ionut")
    config.POLISHED_DIR.mkdir(parents=True, exist_ok=True)
    (config.POLISHED_DIR / "2025-09-01_corrupt.json").write_text(
        "this is not valid json {{{", encoding="utf-8"
    )

    added = corpus.reconcile_from_polished()

    # Valid file is indexed; corrupt file is skipped.
    assert added == 1
    entries = corpus.load()
    assert len(entries) == 1
    assert entries[0]["file_id"] == "2025-08-07_vasquez__ionut_en"
    # Warning emitted about the corrupt file.
    assert any("reconcile: skipping" in rec.message and "corrupt" in rec.message
               for rec in caplog.records)


def test_reconcile_warns_on_missing_participants(tmp_project, caplog):
    import json
    import logging
    caplog.set_level(logging.WARNING)
    import config
    from persons import corpus

    # Polished JSON with NO participants field.
    config.POLISHED_DIR.mkdir(parents=True, exist_ok=True)
    (config.POLISHED_DIR / "2025-08-07_noparts_en.json").write_text(
        json.dumps({
            "file_id": "2025-08-07_noparts_en",
            "date": "2025-08-07",
            "language": "en",
            "duration_s": 60.0,
            "segments": [],
            # no 'participants' field
        }),
        encoding="utf-8",
    )

    added = corpus.reconcile_from_polished()

    assert added == 1  # still indexed, just with a warning
    entries = corpus.load()
    assert len(entries) == 1
    assert "teacher_id" not in entries[0]
    assert "student_id" not in entries[0]
    # Warning must mention the missing participants.
    assert any("no teacher_id/student_id" in rec.message or "participants" in rec.message
               for rec in caplog.records)
