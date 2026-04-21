"""
Unit tests for the Gate 5C low-risk daemon handlers.

Each handler is a `(cmd, emit) -> None` function. Tests inject a
list.append sink as the emit callable so we can assert the sequence of
events (type + fields). No subprocesses spawned here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    monkeypatch.setenv("VERBATIM_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod in ("config", "handlers", "run", "filename_parser") or mod.startswith("persons"):
            sys.modules.pop(mod, None)
    yield tmp_path


def _sink():
    captured: list = []
    return captured, captured.append


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

def test_detect_reports_cpu_and_flags(tmp_project, monkeypatch):
    from ipc_protocol import DetectCommand, SystemInfoEvent
    import handlers

    monkeypatch.setenv("HF_TOKEN", "secret-hf")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured, emit = _sink()
    handlers.handle_detect(DetectCommand(id="d-1"), emit)

    assert len(captured) == 1
    evt = captured[0]
    assert isinstance(evt, SystemInfoEvent)
    assert evt.id == "d-1"
    assert evt.hf_token is True
    assert evt.anthropic_api_key is False
    assert evt.cpu.get("logical_cores", 0) > 0
    assert evt.disk_free_gb >= 0.0


# ---------------------------------------------------------------------------
# list_persons
# ---------------------------------------------------------------------------

def test_list_persons_empty_registry_returns_empty_list(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import ListPersonsCommand, PersonsListedEvent
    import handlers

    captured, emit = _sink()
    handlers.handle_list_persons(ListPersonsCommand(id="l-1"), emit)

    assert isinstance(captured[0], PersonsListedEvent)
    assert captured[0].id == "l-1"
    assert captured[0].persons == []


def test_list_persons_returns_registered_records(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import ListPersonsCommand, PersonsListedEvent
    from persons import registry
    import handlers

    registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    registry.register_new(
        id_="ionut", display_name="ionut",
        default_role="student", first_seen="2025-08-07",
    )

    captured, emit = _sink()
    handlers.handle_list_persons(ListPersonsCommand(id="l-2"), emit)

    assert isinstance(captured[0], PersonsListedEvent)
    ids = sorted(p["id"] for p in captured[0].persons)
    assert ids == ["ionut", "vasquez"]


# ---------------------------------------------------------------------------
# register_person
# ---------------------------------------------------------------------------

def test_register_person_happy_path(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import PersonRegisteredEvent, RegisterPersonCommand
    import handlers

    cmd = RegisterPersonCommand(id="r-1", person={
        "id": "alessandro",
        "display_name": "Alessandro",
        "default_role": "teacher",
        "voice_type": "tenor",
    })
    captured, emit = _sink()
    handlers.handle_register_person(cmd, emit)

    assert isinstance(captured[0], PersonRegisteredEvent)
    assert captured[0].person_id == "alessandro"
    assert captured[0].record["voice_type"] == "tenor"


def test_register_person_missing_fields_emits_error(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import ErrorEvent, RegisterPersonCommand
    import handlers

    cmd = RegisterPersonCommand(id="r-2", person={"id": "x"})  # no display_name
    captured, emit = _sink()
    handlers.handle_register_person(cmd, emit)

    assert isinstance(captured[0], ErrorEvent)
    assert captured[0].error_type == "invalid_command_payload"
    assert "display_name" in captured[0].message


def test_register_person_duplicate_name_emits_error(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import ErrorEvent, RegisterPersonCommand
    from persons import registry
    import handlers

    registry.register_new(
        id_="ionut", display_name="Ionuț", default_role="student",
        first_seen="2025-08-07",
    )
    cmd = RegisterPersonCommand(id="r-3", person={
        "id": "ionut_2", "display_name": "Ionuț", "default_role": "student",
    })
    captured, emit = _sink()
    handlers.handle_register_person(cmd, emit)

    assert isinstance(captured[0], ErrorEvent)
    assert "display_name" in captured[0].message


# ---------------------------------------------------------------------------
# inspect_person
# ---------------------------------------------------------------------------

def test_inspect_person_returns_record_and_lists_npy_files(tmp_project):
    import config  # noqa: F401
    import numpy as np
    from ipc_protocol import InspectPersonCommand, PersonInspectedEvent
    from persons import registry
    import handlers

    registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    pdir = registry.person_dir("vasquez")
    np.save(pdir / "universal.npy", np.zeros(512, dtype=np.float32))
    np.save(pdir / "speaking.npy", np.zeros(512, dtype=np.float32))

    captured, emit = _sink()
    handlers.handle_inspect_person(InspectPersonCommand(id="i-1", person_id="vasquez"), emit)

    assert isinstance(captured[0], PersonInspectedEvent)
    assert captured[0].person["id"] == "vasquez"
    assert sorted(captured[0].voiceprint_files) == ["speaking.npy", "universal.npy"]


def test_inspect_person_unknown_id_emits_error(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import ErrorEvent, InspectPersonCommand
    import handlers

    captured, emit = _sink()
    handlers.handle_inspect_person(InspectPersonCommand(id="i-2", person_id="ghost"), emit)
    assert isinstance(captured[0], ErrorEvent)
    assert "not found" in captured[0].message


# ---------------------------------------------------------------------------
# edit_person
# ---------------------------------------------------------------------------

def test_edit_person_updates_voice_type_and_emits_fresh_inspect(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import EditPersonCommand, PersonInspectedEvent
    from persons import registry
    import handlers

    registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )

    captured, emit = _sink()
    handlers.handle_edit_person(
        EditPersonCommand(id="e-1", person_id="vasquez", updates={"voice_type": "tenor"}),
        emit,
    )
    assert isinstance(captured[0], PersonInspectedEvent)
    assert captured[0].person["voice_type"] == "tenor"
    # Check persisted on disk too.
    assert registry.load("vasquez").voice_type == "tenor"


def test_edit_person_rejects_immutable_fields(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import EditPersonCommand, ErrorEvent
    from persons import registry
    import handlers

    registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    captured, emit = _sink()
    handlers.handle_edit_person(
        EditPersonCommand(id="e-2", person_id="vasquez",
                          updates={"id": "nope", "n_sessions_as_teacher": 99}),
        emit,
    )
    assert isinstance(captured[0], ErrorEvent)
    assert "immutable" in captured[0].message
    # And the record was not mutated.
    assert registry.load("vasquez").n_sessions_as_teacher == 0


# ---------------------------------------------------------------------------
# rename_person
# ---------------------------------------------------------------------------

def test_rename_person_happy_path(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import PersonRenamedEvent, RenamePersonCommand
    from persons import registry
    import handlers

    registry.register_new(
        id_="ionut", display_name="ionut", default_role="student",
        first_seen="2025-08-07",
    )
    captured, emit = _sink()
    handlers.handle_rename_person(
        RenamePersonCommand(id="rn-1", old_id="ionut", new_id="ionut_v2"),
        emit,
    )
    assert isinstance(captured[0], PersonRenamedEvent)
    assert captured[0].old_id == "ionut"
    assert captured[0].new_id == "ionut_v2"
    assert registry.exists("ionut_v2")
    assert not registry.exists("ionut")


def test_rename_person_unknown_old_id_emits_error(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import ErrorEvent, RenamePersonCommand
    import handlers

    captured, emit = _sink()
    handlers.handle_rename_person(
        RenamePersonCommand(id="rn-2", old_id="ghost", new_id="ghost_v2"),
        emit,
    )
    assert isinstance(captured[0], ErrorEvent)


# ---------------------------------------------------------------------------
# merge_persons
# ---------------------------------------------------------------------------

def test_merge_persons_happy_path(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import MergePersonsCommand, PersonMergedEvent
    from persons import registry
    import handlers

    registry.register_new(
        id_="a", display_name="A",
        default_role="teacher", first_seen="2025-08-07",
    )
    registry.register_new(
        id_="b", display_name="B",
        default_role="teacher", first_seen="2025-08-07",
    )

    captured, emit = _sink()
    handlers.handle_merge_persons(
        MergePersonsCommand(id="m-1", source_id="a", target_id="b"),
        emit,
    )
    assert isinstance(captured[0], PersonMergedEvent)
    assert registry.exists("b")
    assert not registry.exists("a")


def test_merge_persons_same_id_emits_error(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import ErrorEvent, MergePersonsCommand
    import handlers

    captured, emit = _sink()
    handlers.handle_merge_persons(
        MergePersonsCommand(id="m-2", source_id="x", target_id="x"),
        emit,
    )
    assert isinstance(captured[0], ErrorEvent)
    assert "differ" in captured[0].message


# ---------------------------------------------------------------------------
# scan_files
# ---------------------------------------------------------------------------

def test_scan_files_enumerates_audio_with_meta(tmp_project, monkeypatch):
    import config  # noqa: F401
    from ipc_protocol import FilesScannedEvent, ScanFilesCommand
    import handlers

    input_dir = tmp_project / "Material"
    input_dir.mkdir()
    # Valid filename — filename_parser accepts it.
    (input_dir / "2025-08-07_vasquez__ionut_en.mp4").write_bytes(b"fake-binary")
    # Non-audio should be skipped.
    (input_dir / "notes.txt").write_bytes(b"ignore me")

    captured, emit = _sink()
    handlers.handle_scan_files(
        ScanFilesCommand(id="s-1", input_dir=str(input_dir), probe_duration=False),
        emit,
    )
    assert isinstance(captured[0], FilesScannedEvent)
    assert len(captured[0].files) == 1
    entry = captured[0].files[0]
    assert entry["name"] == "2025-08-07_vasquez__ionut_en.mp4"
    assert entry["meta"]["parse_ok"] is True
    assert entry["meta"]["teacher_id"] == "vasquez"


def test_scan_files_bad_dir_emits_error(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import ErrorEvent, ScanFilesCommand
    import handlers

    captured, emit = _sink()
    handlers.handle_scan_files(
        ScanFilesCommand(id="s-2", input_dir=str(tmp_project / "does_not_exist")),
        emit,
    )
    assert isinstance(captured[0], ErrorEvent)


# ---------------------------------------------------------------------------
# get_corpus_summary
# ---------------------------------------------------------------------------

def test_get_corpus_summary_empty_is_fine(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import CorpusSummaryEvent, GetCorpusSummaryCommand
    import handlers

    captured, emit = _sink()
    handlers.handle_get_corpus_summary(GetCorpusSummaryCommand(id="c-1"), emit)
    assert isinstance(captured[0], CorpusSummaryEvent)
    assert captured[0].session_count == 0
    assert captured[0].persons == {}
    assert captured[0].total_hours == 0.0


def test_get_corpus_summary_counts_sessions_and_hours(tmp_project):
    import config  # noqa: F401
    from ipc_protocol import CorpusSummaryEvent, GetCorpusSummaryCommand
    from persons import corpus, registry
    import handlers

    v = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    v.n_sessions_as_teacher = 3
    v.total_hours = 2.5
    registry.save(v)
    corpus.append_session({
        "file_id": "2025-08-07_vasquez__ionut_en",
        "date": "2025-08-07", "language": "en",
        "teacher_id": "vasquez", "student_id": "ionut",
    })

    captured, emit = _sink()
    handlers.handle_get_corpus_summary(GetCorpusSummaryCommand(id="c-2"), emit)
    evt = captured[0]
    assert isinstance(evt, CorpusSummaryEvent)
    assert evt.session_count == 1
    assert evt.persons["vasquez"]["sessions_as_teacher"] == 3
    assert evt.total_hours == 2.5


# ---------------------------------------------------------------------------
# cancel_batch
# ---------------------------------------------------------------------------

def test_cancel_batch_sets_flag_and_acks(tmp_project):
    from ipc_protocol import CancelAcceptedEvent, CancelBatchCommand
    from utils import cancellation
    import handlers

    cancellation.reset()
    assert not cancellation.cancelled()

    captured, emit = _sink()
    handlers.handle_cancel_batch(CancelBatchCommand(id="x-1"), emit)

    assert isinstance(captured[0], CancelAcceptedEvent)
    assert captured[0].id == "x-1"
    assert cancellation.cancelled(), "cancel_batch must set the flag"
    cancellation.reset()  # leave clean for next test
