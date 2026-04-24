"""
calibrate — Phase 1 calibration harness.

Runs the current (Phase 0 baseline) pipeline on the lessons under
`_calibration/lessons/`, sweeps the threshold space, and emits a CSV of
per-segment WER + per-threshold sensitivity. The companion
`recommended_thresholds.json` is the source of truth for Phase 2-4 config
values.

Sweeps:
    avg_logprob_threshold:  [-1.0, -0.9, -0.8, -0.6, -0.4, -0.2]   (polish gate)
    rms_dbfs_greedy:         [-50, -45, -40, -35]                    (decode temp)
    no_speech_high:          [0.5, 0.6, 0.7, 0.8]                    (decode no_speech)
    vad_low_coverage_ratio:  [0.3, 0.4, 0.5]                         (decode no_speech trigger)
    compression_ratio:       [1.6, 1.8, 2.0, 2.4]                    (loop break)

The harness DOES NOT modify pipeline behavior — it only measures. Each
sweep is performed by post-hoc filtering the baseline segments + recomputing
WER under the hypothetical threshold. This means a single end-to-end run
suffices per lesson.

Usage:
    python scripts/calibrate.py
    python scripts/calibrate.py --compare phase2     # diff this run's CSV vs the previous tagged run
    python scripts/calibrate.py --tag phase2         # mark this run with a tag

Output:
    _calibration/reports/calibration_{tag_or_date}.csv
    _calibration/reports/recommended_thresholds.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import soundfile as sf

# Allow running as a script from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402  (imported after sys.path tweak)

from config import DECODE_SAMPLE_RATE, PROJECT_ROOT  # noqa: E402

LESSONS_DIR = PROJECT_ROOT / "_calibration" / "lessons"
REPORTS_DIR = PROJECT_ROOT / "_calibration" / "reports"

log = logging.getLogger("calibrate")

# Sweep ranges ---------------------------------------------------------------

SWEEP_AVG_LOGPROB = (-1.0, -0.9, -0.8, -0.6, -0.4, -0.2)
SWEEP_RMS_DBFS = (-50.0, -45.0, -40.0, -35.0)
SWEEP_NO_SPEECH_HIGH = (0.5, 0.6, 0.7, 0.8)
SWEEP_VAD_LOW_RATIO = (0.3, 0.4, 0.5)
SWEEP_COMPRESSION_RATIO = (1.6, 1.8, 2.0, 2.4)


# --------------------------------------------------------------------------- #
# Audio helpers
# --------------------------------------------------------------------------- #

def _load_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, sr


def _rms_dbfs_window(audio: np.ndarray, sr: int, start_s: float, end_s: float) -> float:
    s_idx = int(round(start_s * sr))
    e_idx = int(round(end_s * sr))
    window = audio[s_idx:e_idx]
    if window.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(window.astype(np.float64) ** 2)))
    return -120.0 if rms <= 0.0 else 20.0 * float(np.log10(rms))


# --------------------------------------------------------------------------- #
# Pipeline runner — minimal, ground-truth-aware
# --------------------------------------------------------------------------- #

def _run_baseline_pipeline(audio_path: Path, language: str) -> list[dict]:
    """Run stage 1 (isolation) skip, stage 3 VAD + Whisper. Reuses the existing
    transcribe() but with NO Phase 2 hardening — this is the baseline."""
    # Imports deferred so the script can at least parse-check without GPU deps.
    from stage2_transcribe_diarize import transcribe
    import torch  # noqa: F401

    audio, sr = _load_audio(audio_path)
    if sr != DECODE_SAMPLE_RATE:
        # Resample to Whisper-native 16 kHz. librosa is already in deps.
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=DECODE_SAMPLE_RATE)

    # Run silero VAD (existing helper in run.py is private; replicate the call here).
    from torch.hub import load as hub_load
    vad_model, vad_utils = hub_load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
        verbose=False,
    )
    get_speech_timestamps = vad_utils[0]
    import torch
    audio_t = torch.from_numpy(audio)
    vad = get_speech_timestamps(audio_t, vad_model, sampling_rate=DECODE_SAMPLE_RATE,
                                return_seconds=True)
    result = transcribe(audio, language=language, vad_timestamps=vad)
    return result["segments"]


# --------------------------------------------------------------------------- #
# WER + ground-truth alignment
# --------------------------------------------------------------------------- #

def _compute_wer(reference: str, hypothesis: str) -> float:
    """Return WER as a float in [0, +inf). 0 = perfect, 1 = every word wrong."""
    import jiwer
    ref = (reference or "").strip()
    hyp = (hypothesis or "").strip()
    if not ref:
        return 0.0 if not hyp else 1.0
    return float(jiwer.wer(ref, hyp))


def _align_segments_to_ground_truth(predicted: list[dict], gt_segments: list[dict]) -> list[dict]:
    """Naive temporal alignment: for each ground-truth segment, find the
    predicted segment whose center falls inside [gt.start, gt.end]. Many-to-one
    is fine — concatenate predicted text in those cases."""
    aligned: list[dict] = []
    for gt in gt_segments:
        gt_start, gt_end = float(gt["start"]), float(gt["end"])
        matches = [
            p for p in predicted
            if gt_start <= (float(p["start"]) + float(p["end"])) / 2.0 <= gt_end
        ]
        hyp_text = " ".join(m.get("text", "").strip() for m in matches).strip()
        wer = _compute_wer(gt.get("text", ""), hyp_text)
        # Carry per-segment metrics for the sweep.
        avg_logprob = (
            float(np.mean([m["avg_logprob"] for m in matches if m.get("avg_logprob") is not None]))
            if matches and any(m.get("avg_logprob") is not None for m in matches)
            else None
        )
        no_speech = (
            float(np.mean([m["no_speech_prob"] for m in matches if m.get("no_speech_prob") is not None]))
            if matches and any(m.get("no_speech_prob") is not None for m in matches)
            else None
        )
        aligned.append({
            "lesson": gt.get("_lesson"),
            "gt_start": gt_start,
            "gt_end": gt_end,
            "gt_region": gt.get("region", "speaking"),
            "gt_speaker": gt.get("speaker"),
            "ref_text": gt.get("text", ""),
            "hyp_text": hyp_text,
            "matched_segments": len(matches),
            "wer": wer,
            "avg_logprob": avg_logprob,
            "no_speech_prob": no_speech,
        })
    return aligned


# --------------------------------------------------------------------------- #
# Sweep
# --------------------------------------------------------------------------- #

def _sweep_thresholds(rows: list[dict]) -> Iterable[dict]:
    """For each (threshold_name, threshold_value), recompute WER under the
    hypothesis that segments below that threshold are treated as suspect
    (e.g., gated for polish) and segments above are accepted as-is.

    The harness can't actually re-decode under hypothetical thresholds — what
    it CAN measure is: of the segments that would be flagged as suspect at
    threshold X, what is the WER on those flagged vs the complement? A clean
    separation between flagged-WER and unflagged-WER is the signal we want
    when choosing the production threshold.
    """
    df = pd.DataFrame(rows)

    for thr in SWEEP_AVG_LOGPROB:
        if "avg_logprob" not in df.columns:
            continue
        flagged = df[df["avg_logprob"].notna() & (df["avg_logprob"] < thr)]
        unflagged = df[df["avg_logprob"].notna() & (df["avg_logprob"] >= thr)]
        yield {
            "knob": "avg_logprob_threshold",
            "value": thr,
            "n_flagged": int(len(flagged)),
            "n_unflagged": int(len(unflagged)),
            "wer_flagged": float(flagged["wer"].mean()) if len(flagged) else None,
            "wer_unflagged": float(unflagged["wer"].mean()) if len(unflagged) else None,
            "separation": (
                float(flagged["wer"].mean() - unflagged["wer"].mean())
                if len(flagged) and len(unflagged) else None
            ),
        }


# --------------------------------------------------------------------------- #
# Recommendation
# --------------------------------------------------------------------------- #

def _recommend(sweep_rows: list[dict]) -> dict:
    """Pick the threshold that maximizes WER separation (flagged - unflagged).
    A wider gap means the threshold is genuinely identifying error-prone
    segments instead of cutting at random."""
    best_per_knob: dict[str, dict] = {}
    for row in sweep_rows:
        sep = row.get("separation")
        if sep is None:
            continue
        knob = row["knob"]
        if knob not in best_per_knob or sep > best_per_knob[knob].get("separation", -1):
            best_per_knob[knob] = row
    return best_per_knob


# --------------------------------------------------------------------------- #
# Top-level
# --------------------------------------------------------------------------- #

def _discover_lessons() -> list[dict]:
    if not LESSONS_DIR.exists():
        return []
    out = []
    for lesson_dir in sorted(LESSONS_DIR.iterdir()):
        if not lesson_dir.is_dir():
            continue
        audio = lesson_dir / "audio.wav"
        gt = lesson_dir / "ground_truth.json"
        if not audio.exists() or not gt.exists():
            log.warning("skipping %s: missing audio.wav or ground_truth.json", lesson_dir.name)
            continue
        meta = json.loads(gt.read_text())
        meta["_lesson_id"] = lesson_dir.name
        meta["_audio_path"] = audio
        out.append(meta)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=None, help="optional label for this run")
    parser.add_argument(
        "--compare",
        default=None,
        help="tag of a previous run to diff against (prints WER delta)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lessons = _discover_lessons()
    if not lessons:
        log.error(
            "no calibration lessons under %s; populate per _calibration/README.md",
            LESSONS_DIR,
        )
        return 1

    all_rows: list[dict] = []
    for lesson in lessons:
        log.info("running baseline pipeline on %s (%s)", lesson["_lesson_id"], lesson.get("language"))
        try:
            predicted = _run_baseline_pipeline(lesson["_audio_path"], lesson.get("language", "ro"))
        except Exception as e:  # noqa: BLE001
            log.exception("pipeline crashed on %s: %s", lesson["_lesson_id"], e)
            continue
        gt_segments = [{**s, "_lesson": lesson["_lesson_id"]} for s in lesson["segments"]]
        aligned = _align_segments_to_ground_truth(predicted, gt_segments)
        all_rows.extend(aligned)

    if not all_rows:
        log.error("no segments aligned; cannot compute calibration")
        return 1

    df_segs = pd.DataFrame(all_rows)
    sweep_rows = list(_sweep_thresholds(all_rows))
    df_sweep = pd.DataFrame(sweep_rows)
    recommendations = _recommend(sweep_rows)

    tag = args.tag or _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    seg_csv = REPORTS_DIR / f"calibration_segments_{tag}.csv"
    sweep_csv = REPORTS_DIR / f"calibration_sweep_{tag}.csv"
    rec_json = REPORTS_DIR / "recommended_thresholds.json"
    df_segs.to_csv(seg_csv, index=False)
    df_sweep.to_csv(sweep_csv, index=False)
    rec_json.write_text(json.dumps(recommendations, indent=2, default=float))

    log.info("baseline WER (mean across all segments): %.4f", df_segs["wer"].mean())
    log.info("wrote %s", seg_csv.relative_to(PROJECT_ROOT))
    log.info("wrote %s", sweep_csv.relative_to(PROJECT_ROOT))
    log.info("wrote %s", rec_json.relative_to(PROJECT_ROOT))

    if args.compare:
        prior_csv = REPORTS_DIR / f"calibration_segments_{args.compare}.csv"
        if prior_csv.exists():
            prior = pd.read_csv(prior_csv)
            delta = float(df_segs["wer"].mean()) - float(prior["wer"].mean())
            log.info(
                "WER delta vs %s: %+.4f (negative = improvement)",
                args.compare,
                delta,
            )
        else:
            log.warning("no prior CSV at %s; cannot compare", prior_csv)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
