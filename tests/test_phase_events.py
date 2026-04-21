"""
Phase-event wiring: _process_one, _transcribe_align_diarize, and _finalize
emit phase_started / phase_complete events for every phase named in
ipc_protocol.PHASE_NAMES (excluding isolation, which lives at the batch
handler level since stage-1 is a pre-pass).

Tests heavily mock the ML-heavy modules so no GPU is required.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


def _capture_reporter(cmd_id: str = "t-1"):
    from utils.reporter import CallbackReporter
    captured: list = []
    reporter = CallbackReporter(captured.append, cmd_id=cmd_id)
    return captured, reporter


@pytest.fixture
def stub_stage2(monkeypatch):
    """Replace stage2_transcribe_diarize with stubs that just return the
    data shapes _process_one expects downstream."""
    mod = types.ModuleType("stage2_transcribe_diarize")
    mod.transcribe = MagicMock(return_value={"segments": [{"start": 0.0, "end": 1.0, "text": "hi"}]})
    mod.align = MagicMock(return_value=[{"start": 0.0, "end": 1.0, "text": "hi", "words": []}])
    mod.diarize = MagicMock(return_value=MagicMock(name="diar_df"))
    mod.attach_speaker_labels = MagicMock(
        return_value=[{"start": 0.0, "end": 1.0, "text": "hi", "speaker": "SPEAKER_00"}]
    )
    mod.cluster_embeddings_from_segments = MagicMock(
        return_value={"SPEAKER_00": np.zeros(512, dtype=np.float32)}
    )
    monkeypatch.setitem(sys.modules, "stage2_transcribe_diarize", mod)
    return mod


@pytest.fixture
def stub_stage3(monkeypatch):
    mod = types.ModuleType("stage3_postprocess")
    mod.identify_speakers = MagicMock(return_value=([], {}))
    mod.run_verification = MagicMock(return_value=[])
    mod.polish = MagicMock(return_value=[])
    mod.update_voice_libraries = MagicMock()
    mod.stamp_db_state = MagicMock()
    mod.finalize = MagicMock()
    monkeypatch.setitem(sys.modules, "stage3_postprocess", mod)
    return mod


def test_transcribe_align_diarize_emits_asr_alignment_diarization(stub_stage2):
    import run
    audio = np.zeros(16000, dtype=np.float32)
    captured, reporter = _capture_reporter()

    run._transcribe_align_diarize(audio, "en", [(0.0, 1.0)], reporter=reporter, file_index=0)

    phases_started = [(e.phase, e.phase_index) for e in captured if e.type == "phase_started"]
    phases_complete = [e.phase for e in captured if e.type == "phase_complete"]

    assert phases_started == [("asr", 4), ("alignment", 5), ("diarization", 6)]
    assert phases_complete == ["asr", "alignment", "diarization"]
    # Complete events carry elapsed_s >= 0.
    for e in captured:
        if e.type == "phase_complete":
            assert e.elapsed_s >= 0.0


def test_finalize_emits_identification_verification_polish_corpus_update(
    tmp_path, stub_stage3, monkeypatch,
):
    monkeypatch.setenv("VERBATIM_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "config" or mod.startswith("persons") or mod == "run":
            sys.modules.pop(mod, None)

    import run
    # source_codec_info hits ffprobe — stub it out
    fake_qc = types.SimpleNamespace(
        overlap_ratio=lambda *a, **kw: 0.0,
        source_codec_info=lambda *a, **kw: {"codec": "aac", "bitrate": 128000},
    )
    monkeypatch.setitem(sys.modules, "utils.audio_qc", fake_qc)
    # render_display requires persons.schema + utils.text_norm — neutral stub
    fake_schema = types.SimpleNamespace(render_display=lambda p: "x")
    monkeypatch.setitem(sys.modules, "persons.schema", fake_schema)

    from filename_parser import SessionMeta
    meta = SessionMeta(
        date="2025-08-07", language="en",
        teacher_id="t", student_id="s",
        source_path=Path("x.mp4"),
    )
    audio = np.zeros(1600, dtype=np.float32)

    captured, reporter = _capture_reporter()
    run._finalize(
        source=Path("x.mp4"), acapella=Path("x.wav"),
        audio=audio,
        labeled_segments=[],
        cluster_emb={},
        meta=meta, fid="2025-08-07_t__s_en",
        reporter=reporter, file_index=2,
    )

    phases_started = [(e.phase, e.phase_index) for e in captured if e.type == "phase_started"]
    phases_complete = [e.phase for e in captured if e.type == "phase_complete"]
    assert phases_started == [
        ("identification", 7),
        ("verification", 8),
        ("polish", 9),
        ("corpus_update", 10),
    ]
    assert phases_complete == ["identification", "verification", "polish", "corpus_update"]
    # All phase events carry our file_index.
    for e in captured:
        if e.type in ("phase_started", "phase_complete"):
            assert e.file_index == 2


def test_phase_index_matches_ipc_protocol():
    """Guard: the phase_index emitted must match PHASE_NAMES.index + 1."""
    from ipc_protocol import PHASE_NAMES
    import run

    for i, name in enumerate(PHASE_NAMES, start=1):
        assert run._phase_index(name) == i


def test_process_one_propagates_cancellation(monkeypatch, tmp_path, stub_stage2, stub_stage3):
    """cancel_check() between phases must raise CancelledError out of
    _process_one so the outer batch can stop cleanly."""
    import asyncio
    import run
    from utils import cancellation

    monkeypatch.setattr(run, "_decode_acapella", lambda p: np.zeros(16000, dtype=np.float32))
    monkeypatch.setattr(run, "_run_vad", lambda a: [(0.0, 1.0)])
    monkeypatch.setattr(run, "_transcribe_align_diarize",
                        lambda *a, **kw: ([], {"SPEAKER_00": np.zeros(512, dtype=np.float32)}))
    monkeypatch.setattr(run, "_finalize", lambda *a, **kw: None)

    cancellation.reset()
    cancellation.request_cancel()

    captured, reporter = _capture_reporter()
    gpu_sem = asyncio.Semaphore(1)

    # Source file must parse. Use a valid Material-style name.
    src = tmp_path / "2025-08-07_vasquez__ionut_en.mp4"
    src.write_bytes(b"")
    acap = tmp_path / "2025-08-07_vasquez__ionut_en.wav"
    acap.write_bytes(b"")

    with pytest.raises(cancellation.CancelledError):
        asyncio.run(
            run._process_one(src, acap, gpu_sem, reporter=reporter, file_index=0)
        )

    cancellation.reset()


def test_process_one_emits_decode_and_vad(monkeypatch, tmp_path, stub_stage2, stub_stage3):
    """Happy-path: decode and vad phase events fire before transcribe."""
    import asyncio
    import run
    from utils import cancellation

    monkeypatch.setattr(run, "_decode_acapella", lambda p: np.zeros(16000, dtype=np.float32))
    monkeypatch.setattr(run, "_run_vad", lambda a: [(0.0, 1.0)])
    monkeypatch.setattr(run, "_transcribe_align_diarize",
                        lambda *a, **kw: ([], {"SPEAKER_00": np.zeros(512, dtype=np.float32)}))
    monkeypatch.setattr(run, "_finalize", lambda *a, **kw: None)

    cancellation.reset()
    captured, reporter = _capture_reporter()
    gpu_sem = asyncio.Semaphore(1)

    src = tmp_path / "2025-08-07_vasquez__ionut_en.mp4"
    src.write_bytes(b"")
    acap = tmp_path / "2025-08-07_vasquez__ionut_en.wav"
    acap.write_bytes(b"")

    ok = asyncio.run(
        run._process_one(src, acap, gpu_sem, reporter=reporter, file_index=5)
    )
    assert ok is True

    started = [e.phase for e in captured if e.type == "phase_started"]
    assert "decode" in started
    assert "vad" in started
    # decode fires before vad.
    assert started.index("decode") < started.index("vad")
    # All events carry our file_index.
    for e in captured:
        if e.type in ("phase_started", "phase_complete"):
            assert e.file_index == 5
