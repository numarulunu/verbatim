"""
Tests for mfa_align.py. Do NOT call real mfa — subprocess is mocked.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    monkeypatch.setenv("VOCALITY_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "config" or mod.startswith("persons") or mod == "mfa_align":
            sys.modules.pop(mod, None)
    yield tmp_path


def _mk_polished(polished_dir: Path, fid: str, segments: list[dict]) -> Path:
    polished_dir.mkdir(parents=True, exist_ok=True)
    path = polished_dir / f"{fid}.json"
    path.write_text(json.dumps({
        "file_id": fid,
        "date": "2025-08-07",
        "language": "en",
        "participants": [{"id": "vasquez", "role": "teacher"}, {"id": "ionut", "role": "student"}],
        "segments": segments,
        "mfa_aligned": False,
    }), encoding="utf-8")
    return path


def _mk_acapella(acap_dir: Path, fid: str) -> Path:
    acap_dir.mkdir(parents=True, exist_ok=True)
    path = acap_dir / f"{fid}.wav"
    # Minimal WAV header + a sliver of PCM so file exists + has shape.
    import soundfile as sf
    import numpy as np
    sf.write(str(path), np.zeros(16000, dtype=np.float32), 16000, subtype="PCM_16")
    return path


def test_compute_overlap_perfect_match(tmp_project):
    import mfa_align
    mfa_words = [{"word": "hello", "start": 0.0, "end": 0.5},
                 {"word": "world", "start": 0.5, "end": 1.0}]
    segments = [{"words_wav2vec2": [
        {"word": "hello", "start": 0.01},
        {"word": "world", "start": 0.51},
    ]}]
    assert mfa_align._compute_overlap(mfa_words, segments) == 1.0


def test_compute_overlap_partial(tmp_project):
    import mfa_align
    mfa_words = [{"word": "hello", "start": 0.0},
                 {"word": "world", "start": 0.5},
                 {"word": "extra", "start": 1.0}]
    segments = [{"words_wav2vec2": [
        {"word": "hello", "start": 0.0},
        {"word": "world", "start": 0.5},
    ]}]
    assert mfa_align._compute_overlap(mfa_words, segments) == pytest.approx(2/3)


def test_compute_overlap_empty_inputs(tmp_project):
    import mfa_align
    assert mfa_align._compute_overlap([], [{}]) == 0.0
    assert mfa_align._compute_overlap([{"word": "x", "start": 0.0}], []) == 0.0


def test_align_one_missing_polished(tmp_project):
    import mfa_align
    assert mfa_align.align_one("nonexistent") is False


def test_align_one_missing_acapella(tmp_project):
    import config
    import mfa_align
    _mk_polished(config.POLISHED_DIR, "2025-01-01_ionut__madalina_en",
                 segments=[{"start": 0.0, "end": 1.0, "text": "hello world"}])
    # No acapella written — align_one should bail.
    assert mfa_align.align_one("2025-01-01_ionut__madalina_en") is False


def test_align_one_mfa_not_on_path(tmp_project, monkeypatch):
    import config
    import mfa_align
    _mk_polished(config.POLISHED_DIR, "2025-01-01_ionut__madalina_en",
                 segments=[{"start": 0.0, "end": 1.0, "text": "hello world"}])
    _mk_acapella(config.ACAPELLA_DIR, "2025-01-01_ionut__madalina_en")
    monkeypatch.setattr("shutil.which", lambda name: None)  # mfa not on PATH
    assert mfa_align.align_one("2025-01-01_ionut__madalina_en") is False


def test_align_one_rejects_low_overlap(tmp_project, monkeypatch):
    """If MFA output has <95% word overlap with wav2vec2, reject and don't touch words_mfa."""
    import config
    import mfa_align
    fid = "2025-01-01_ionut__madalina_en"
    polished_path = _mk_polished(
        config.POLISHED_DIR, fid,
        segments=[{
            "start": 0.0, "end": 2.0, "text": "hello world",
            "words_wav2vec2": [
                {"word": "hello", "start": 0.0, "end": 0.5},
                {"word": "world", "start": 0.5, "end": 1.0},
            ],
        }],
    )
    _mk_acapella(config.ACAPELLA_DIR, fid)

    monkeypatch.setattr("shutil.which", lambda name: "/fake/mfa")

    def fake_run(cmd, **kwargs):
        out_dir = Path(cmd[5])   # positional output_directory (cmd: mfa align corpus dict model out --clean)
        (out_dir / "speaker_01").mkdir(parents=True, exist_ok=True)
        (out_dir / "speaker_01" / f"{fid}.TextGrid").write_text("", encoding="utf-8")
        return MagicMock(returncode=0, stderr="", stdout="")
    monkeypatch.setattr("subprocess.run", fake_run)

    def fake_parse(path):
        # Returns words totally unlike wav2vec2 -> overlap 0%.
        return [
            {"word": "goodbye", "start": 0.0, "end": 0.5},
            {"word": "universe", "start": 0.5, "end": 1.0},
        ]
    monkeypatch.setattr(mfa_align, "_parse_textgrid", fake_parse)

    assert mfa_align.align_one(fid) is False

    # Polished JSON must be unchanged (no words_mfa added, mfa_aligned still False).
    data = json.loads(polished_path.read_text(encoding="utf-8"))
    assert data["mfa_aligned"] is False
    assert "words_mfa" not in data["segments"][0]


def test_align_one_accepts_high_overlap(tmp_project, monkeypatch):
    """MFA output with 100% overlap -> words_mfa written, mfa_aligned=True."""
    import config
    import mfa_align
    fid = "2025-01-01_ionut__madalina_en"
    polished_path = _mk_polished(
        config.POLISHED_DIR, fid,
        segments=[{
            "start": 0.0, "end": 2.0, "text": "hello world",
            "words_wav2vec2": [
                {"word": "hello", "start": 0.0, "end": 0.5},
                {"word": "world", "start": 0.5, "end": 1.0},
            ],
        }],
    )
    _mk_acapella(config.ACAPELLA_DIR, fid)

    monkeypatch.setattr("shutil.which", lambda name: "/fake/mfa")

    def fake_run(cmd, **kwargs):
        out_dir = Path(cmd[5])   # positional output_directory (cmd: mfa align corpus dict model out --clean)
        (out_dir / "speaker_01").mkdir(parents=True, exist_ok=True)
        (out_dir / "speaker_01" / f"{fid}.TextGrid").write_text("", encoding="utf-8")
        return MagicMock(returncode=0, stderr="", stdout="")
    monkeypatch.setattr("subprocess.run", fake_run)

    def fake_parse(path):
        return [
            {"word": "hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.5, "end": 1.0},
        ]
    monkeypatch.setattr(mfa_align, "_parse_textgrid", fake_parse)

    assert mfa_align.align_one(fid) is True

    data = json.loads(polished_path.read_text(encoding="utf-8"))
    assert data["mfa_aligned"] is True
    assert len(data["segments"][0]["words_mfa"]) == 2
    assert data["segments"][0]["words_mfa"][0]["word"] == "hello"


def test_verify_returns_zero_when_no_words_mfa(tmp_project):
    import config
    import mfa_align
    fid = "2025-01-01_x"
    path = _mk_polished(
        config.POLISHED_DIR, fid,
        segments=[{"start": 0.0, "end": 1.0, "text": "hi",
                   "words_wav2vec2": [{"word": "hi", "start": 0.0, "end": 0.5}]}],
    )
    assert mfa_align.verify(path) == 0.0


def test_verify_reports_overlap(tmp_project):
    import config
    import mfa_align
    fid = "2025-01-01_x"
    path = _mk_polished(
        config.POLISHED_DIR, fid,
        segments=[{
            "start": 0.0, "end": 1.0, "text": "hi there",
            "words_wav2vec2": [
                {"word": "hi", "start": 0.0, "end": 0.5},
                {"word": "there", "start": 0.5, "end": 1.0},
            ],
            "words_mfa": [
                {"word": "hi", "start": 0.0, "end": 0.5},
                {"word": "there", "start": 0.5, "end": 1.0},
            ],
        }],
    )
    assert mfa_align.verify(path) == 1.0


def test_discover_by_student_finds_matches(tmp_project):
    import config
    import mfa_align
    _mk_polished(config.POLISHED_DIR, "f1",
                 segments=[{"start": 0, "end": 1, "text": "x"}])
    # Second file with different student.
    (config.POLISHED_DIR / "f2.json").write_text(json.dumps({
        "file_id": "f2", "segments": [],
        "participants": [{"id": "ionut", "role": "teacher"},
                          {"id": "luiza", "role": "student"}],
    }), encoding="utf-8")

    # f1 has 'ionut' as student (per _mk_polished default), f2 has 'luiza'.
    hits_ionut = mfa_align._discover_by_student("ionut")
    hits_luiza = mfa_align._discover_by_student("luiza")
    assert "f1" in hits_ionut and "f2" not in hits_ionut
    assert "f2" in hits_luiza and "f1" not in hits_luiza
