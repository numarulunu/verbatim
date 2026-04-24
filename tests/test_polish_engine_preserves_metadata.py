from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import persons.polish_engine as _pe
from persons.polish_engine import _merge_polished_segments


def _original_segment() -> dict:
    return {
        "start": 1.25,
        "end": 2.5,
        "speaker_id": "ionut",
        "speaker_name": "Ionut Rosu",
        "speaker_role": "teacher",
        "speaker_confidence": 0.87,
        "matched_region": "speaking",
        "region": "speaking",
        "cluster_label": "SPEAKER_00",
        "words": [
            {"word": "old", "start": 1.25, "end": 1.55, "probability": 0.42},
            {"word": "text", "start": 1.56, "end": 2.0, "probability": 0.45},
        ],
        "text": "old text",
        "avg_logprob": -0.8,
    }


def test_merge_polished_segments_preserves_original_metadata() -> None:
    original = [_original_segment()]
    polished = [{"start": 1.25, "end": 2.5, "speaker_id": "ionut", "text": "new text"}]

    out = _merge_polished_segments(original, polished)

    assert out == [
        {
            "start": 1.25,
            "end": 2.5,
            "speaker_id": "ionut",
            "speaker_name": "Ionut Rosu",
            "speaker_role": "teacher",
            "speaker_confidence": 0.87,
            "matched_region": "speaking",
            "region": "speaking",
            "cluster_label": "SPEAKER_00",
            "words": [
                {"word": "old", "start": 1.25, "end": 1.55, "probability": 0.42},
                {"word": "text", "start": 1.56, "end": 2.0, "probability": 0.45},
            ],
            "text": "new text",
            "avg_logprob": -0.8,
            "polished": True,
        }
    ]


def test_merge_polished_segments_does_not_mutate_inputs() -> None:
    original = [_original_segment()]
    polished = [{"start": 1.25, "end": 2.5, "speaker_id": "ionut", "text": "new text"}]

    out = _merge_polished_segments(original, polished)

    assert out is not original
    assert out[0] is not original[0]
    assert original[0]["text"] == "old text"
    assert "polished" not in original[0]
    assert polished == [{"start": 1.25, "end": 2.5, "speaker_id": "ionut", "text": "new text"}]


def test_polish_chunk_cli_preserves_metadata_on_success(monkeypatch) -> None:
    original = [_original_segment()]
    payload = [{"start": 1.25, "end": 2.5, "speaker_id": "ionut", "text": "new text"}]

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(_pe.subprocess, "run", fake_run)

    out = _pe.polish_chunk_cli(original, "en", {"terms": {}})

    assert out[0]["text"] == "new text"
    assert out[0]["speaker_name"] == "Ionut Rosu"
    assert out[0]["speaker_confidence"] == 0.87
    assert out[0]["matched_region"] == "speaking"
    assert out[0]["words"] == original[0]["words"]
    assert out[0]["polished"] is True


def test_polish_chunk_api_preserves_metadata_on_success() -> None:
    original = [_original_segment()]
    payload = [{"start": 1.25, "end": 2.5, "speaker_id": "ionut", "text": "new text"}]

    class FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(payload))]
            )

    class FakeClient:
        messages = FakeMessages()

    out = asyncio.run(_pe.polish_chunk_api(FakeClient(), original, "en", {"terms": {}}))

    assert out[0]["text"] == "new text"
    assert out[0]["speaker_name"] == "Ionut Rosu"
    assert out[0]["speaker_confidence"] == 0.87
    assert out[0]["matched_region"] == "speaking"
    assert out[0]["words"] == original[0]["words"]
    assert out[0]["polished"] is True
