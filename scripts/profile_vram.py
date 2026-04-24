"""
profile_vram — Phase 1 calibration harness.

Loads the three GPU consumers (faster-whisper large-v3-turbo, wav2vec2 aligner,
pyannote 3.1 diarization) sequentially and then co-resident, measures peak
VRAM at each step, writes a verdict to _calibration/reports/.

Decision rule:
    peak_co_resident < 9 GB → parallel-OK (Phase 3 sung branching can run
                              wav2vec2 + Whisper + pyannote concurrently).
    peak_co_resident ≥ 9 GB → SERIALIZE (Phase 3 must explicitly unload
                              wav2vec2 before loading pyannote).

The Mastermind Risk Analyst flagged a kill condition at peak > 10.5 GB
*and* serialized latency > 40 s per 10-min file. That second condition is
not measurable here (no calibrated decode-time numbers yet); this script
only addresses the VRAM question.

Run from repo root:
    python scripts/profile_vram.py
"""
from __future__ import annotations

import datetime as _dt
import gc
import json
import sys
from pathlib import Path

# Allow running as a script from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch  # noqa: E402

from config import (  # noqa: E402
    ALIGN_MODELS,
    DIARIZATION_MODEL,
    HF_TOKEN,
    PROJECT_ROOT,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)

REPORTS_DIR = PROJECT_ROOT / "_calibration" / "reports"


def _bytes_to_gb(n: int) -> float:
    return n / (1024 ** 3)


def _measure(label: str) -> dict[str, float]:
    """Snapshot allocated + reserved VRAM, return GiB."""
    if not torch.cuda.is_available():
        return {"label": label, "allocated_gb": 0.0, "reserved_gb": 0.0, "note": "no CUDA"}
    torch.cuda.synchronize()
    return {
        "label": label,
        "allocated_gb": round(_bytes_to_gb(torch.cuda.memory_allocated()), 3),
        "reserved_gb": round(_bytes_to_gb(torch.cuda.memory_reserved()), 3),
    }


def _free_cuda() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def _load_whisper():
    from faster_whisper import WhisperModel
    return WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)


def _load_wav2vec2():
    # wav2vec2 alignment is exposed via WhisperX in this codebase. Loading the
    # English aligner is enough to size the VRAM footprint; the Romanian
    # aligner (jonatasgrosman) is approximately the same size.
    import whisperx  # type: ignore[import-untyped]
    return whisperx.load_align_model(language_code="en", device=WHISPER_DEVICE)


def _load_pyannote():
    from pyannote.audio import Pipeline
    return Pipeline.from_pretrained(DIARIZATION_MODEL, use_auth_token=HF_TOKEN).to(
        torch.device(WHISPER_DEVICE)
    )


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    measurements: list[dict[str, float | str]] = [_measure("baseline (no models loaded)")]

    print("[profile_vram] loading faster-whisper large-v3-turbo (int8_float32)...")
    whisper = _load_whisper()
    measurements.append(_measure("whisper loaded"))

    print("[profile_vram] loading wav2vec2 aligner...")
    aligner, aligner_meta = _load_wav2vec2()
    measurements.append(_measure("whisper + wav2vec2 loaded"))

    print("[profile_vram] loading pyannote 3.1 diarization...")
    pyannote = _load_pyannote()
    measurements.append(_measure("whisper + wav2vec2 + pyannote (CO-RESIDENT)"))

    co_resident = measurements[-1]["allocated_gb"]
    if co_resident < 9.0:
        verdict = "parallel-ok"
        recommendation = (
            "All three models fit co-resident below the 9 GB threshold. Phase 3 may "
            "load wav2vec2 + Whisper + pyannote concurrently."
        )
    elif co_resident < 10.5:
        verdict = "tight"
        recommendation = (
            "Co-resident within budget but uncomfortably close. Phase 3 should "
            "instrument fallback-to-serial scheduling and warn on first OOM."
        )
    else:
        verdict = "kill-condition"
        recommendation = (
            "Co-resident above 10.5 GB. Per the Mastermind Risk Analyst kill "
            "condition, serialized scheduling is mandatory and the next step is "
            "to measure serialized latency on a 10-minute file. If latency adds "
            ">40 s, the architecture is unshippable on the 1080 Ti."
        )

    # Cleanup so the script doesn't hold VRAM after exit.
    del pyannote, aligner, aligner_meta, whisper
    _free_cuda()

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    report_path = REPORTS_DIR / f"vram_profile_{stamp}.json"
    report = {
        "timestamp_utc": stamp,
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "device_total_gb": round(_bytes_to_gb(torch.cuda.get_device_properties(0).total_memory), 3)
        if torch.cuda.is_available() else None,
        "measurements": measurements,
        "co_resident_peak_gb": co_resident,
        "verdict": verdict,
        "recommendation": recommendation,
    }
    report_path.write_text(json.dumps(report, indent=2))
    print(f"[profile_vram] wrote {report_path.relative_to(PROJECT_ROOT)}")
    print(f"[profile_vram] verdict: {verdict} — {recommendation}")
    return 0 if verdict != "kill-condition" else 2


if __name__ == "__main__":
    raise SystemExit(main())
