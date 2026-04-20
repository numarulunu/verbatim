"""Golden-fixture regression test (Wave 1).

Skipped unless `golden_mixed.wav` exists and its reference is filled in.
Guards against silent accuracy regressions when tuning VAD, initial_prompt,
or diarization params. Intentionally minimal — one fixture, one run, pass/fail.
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"
WAV = FIXTURES / "golden_mixed.wav"
REF = FIXTURES / "golden_mixed.ref.json"


def _load_reference():
    if not REF.exists():
        return None
    try:
        data = json.loads(REF.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not data.get("reference_text"):
        return None
    return data


def _word_error_rate(ref: str, hyp: str) -> float:
    """Standard WER = (S + D + I) / N via Levenshtein on word tokens."""
    r = re.findall(r"\w+", ref.lower())
    h = re.findall(r"\w+", hyp.lower())
    if not r:
        return 0.0
    # Wagner-Fischer on word tokens
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            if r[i - 1] == h[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[len(r)][len(h)] / len(r)


@pytest.mark.integration
@pytest.mark.skipif(
    not WAV.exists() or _load_reference() is None,
    reason="golden_mixed.wav or reference missing — see fixtures/README.md",
)
def test_golden_transcript_wer_within_threshold():
    ref_data = _load_reference()
    assert ref_data is not None

    from core.whisper_pool import WhisperModelPool

    pool = WhisperModelPool()
    pool.initialize(
        model_size="medium",
        language="",  # mixed RO/EN — let auto-detect fire
        beam_size=1,
        initial_prompt="Vocality, Melocchi, Vázquez, passaggio, appoggio, vocalise.",
    )
    result = pool.transcribe(str(WAV))
    hyp = result.get("text", "").strip()
    assert hyp, "whisper returned empty transcript"

    wer = _word_error_rate(ref_data["reference_text"], hyp)
    ceiling = float(ref_data.get("max_wer", 0.25))
    assert wer <= ceiling, f"WER {wer:.3f} exceeds ceiling {ceiling:.3f}"


@pytest.mark.integration
@pytest.mark.skipif(
    not WAV.exists() or _load_reference() is None,
    reason="golden_mixed.wav or reference missing — see fixtures/README.md",
)
def test_golden_diarization_speaker_count():
    ref_data = _load_reference()
    expected = ref_data.get("reference_speakers") or []
    if not expected:
        pytest.skip("reference_speakers not populated")

    from core.diarizer import Diarizer, is_available, get_hf_token
    if not is_available() or not get_hf_token():
        pytest.skip("pyannote unavailable or HF_TOKEN missing")

    d = Diarizer()
    if not d.initialize():
        pytest.skip("diarizer initialize failed")

    segments = d.diarize(str(WAV), num_speakers=0)
    distinct = len({s["speaker"] for s in segments})
    assert distinct >= len(expected), (
        f"diarizer found {distinct} speakers; reference expected at least {len(expected)}"
    )
