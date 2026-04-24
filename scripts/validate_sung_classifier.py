"""
validate_sung_classifier — Phase 1 calibration harness.

Compares two candidate classifiers for the Phase 3 sung-vs-spoken branch
trigger:

    A. persons.regionizer.classify_segment — current pyworld F0 + variance
       implementation (already used elsewhere; tests/test_regionizer_frame_period.py
       locks its frame-period correctness).

    B. ZCR + RMS energy hybrid — Risk Analyst's recommended fallback.
       Sung-candidate iff:  RMS < -30 dBFS  AND  ZCR > 0.3.

Each is run against the labeled audio windows declared in
`_calibration/lessons/{lesson_id}/region_labels.json` (or the aggregate
`_calibration/region_labels.json` if present). Outputs per-classifier
confusion matrix and F1 to `_calibration/reports/sung_classifier_{date}.json`.

Decision rule for Phase 3:
    - Higher-F1 classifier becomes the branch trigger.
    - If both score F1 < 0.8 on sung-region recall, escalate — Phase 3 may
      need a different classifier entirely.

Run from repo root:
    python scripts/validate_sung_classifier.py
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soundfile as sf

# Allow running as a script from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DECODE_SAMPLE_RATE, PROJECT_ROOT  # noqa: E402

LESSONS_DIR = PROJECT_ROOT / "_calibration" / "lessons"
REPORTS_DIR = PROJECT_ROOT / "_calibration" / "reports"

# A label is treated as "sung" iff it starts with "sung". Everything else
# (spoken / whispered / consonant_heavy) is treated as "not-sung". This
# matches the binary nature of the Phase 3 branch trigger.
SUNG_PREFIX = "sung"


# --------------------------------------------------------------------------- #
# Classifier B — ZCR + RMS hybrid
# --------------------------------------------------------------------------- #

def _rms_dbfs(audio: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if rms <= 0.0:
        return -120.0
    return 20.0 * float(np.log10(rms))


def _zero_crossing_rate(audio: np.ndarray) -> float:
    if audio.size < 2:
        return 0.0
    signs = np.signbit(audio)
    return float(np.sum(signs[1:] != signs[:-1])) / float(audio.size - 1)


def classifier_b_zcr_rms(audio: np.ndarray, sr: int) -> str:
    """Risk Analyst's fallback. Returns "sung" or "spoken"."""
    rms = _rms_dbfs(audio)
    zcr = _zero_crossing_rate(audio)
    if rms < -30.0 and zcr > 0.3:
        return "sung"
    return "spoken"


# --------------------------------------------------------------------------- #
# Classifier A — existing pyworld regionizer
# --------------------------------------------------------------------------- #

def classifier_a_pyworld(audio: np.ndarray, sr: int) -> str:
    """Wrap persons.regionizer.classify_segment to return binary sung/spoken."""
    from persons.regionizer import classify_segment

    region = classify_segment(audio, sr)
    return "sung" if str(region).startswith(SUNG_PREFIX) else "spoken"


# --------------------------------------------------------------------------- #
# Eval
# --------------------------------------------------------------------------- #

def _load_labels() -> list[dict]:
    """Load labels from per-lesson region_labels.json files OR a single
    aggregate file at _calibration/region_labels.json."""
    aggregate = PROJECT_ROOT / "_calibration" / "region_labels.json"
    if aggregate.exists():
        return json.loads(aggregate.read_text())["labels"]

    out: list[dict] = []
    if not LESSONS_DIR.exists():
        return out
    for lesson_dir in sorted(LESSONS_DIR.iterdir()):
        if not lesson_dir.is_dir():
            continue
        labels_path = lesson_dir / "region_labels.json"
        if not labels_path.exists():
            continue
        for label in json.loads(labels_path.read_text())["labels"]:
            label.setdefault("file", lesson_dir.name)
            out.append(label)
    return out


def _load_audio_window(file: str, start: float, end: float) -> tuple[np.ndarray, int]:
    audio_path = LESSONS_DIR / file / "audio.wav"
    if not audio_path.exists():
        raise FileNotFoundError(f"missing audio for label: {audio_path}")
    audio, sr = sf.read(audio_path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # mono-fold
    s_idx = int(round(start * sr))
    e_idx = int(round(end * sr))
    return audio[s_idx:e_idx], sr


def _binary_label(raw: str) -> str:
    return "sung" if raw.startswith(SUNG_PREFIX) else "spoken"


def _f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return round(2 * precision * recall / (precision + recall), 4)


def _evaluate(name: str, classifier: Callable[[np.ndarray, int], str], labels: list[dict]) -> dict:
    confusion = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}  # positive class = "sung"
    per_label_results = []
    errors: list[str] = []

    for label in labels:
        gt = _binary_label(label["label"])
        try:
            audio, sr = _load_audio_window(label["file"], label["start"], label["end"])
        except FileNotFoundError as e:
            errors.append(str(e))
            continue
        try:
            pred = classifier(audio, sr)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name} crashed on {label}: {type(e).__name__}: {e}")
            continue
        per_label_results.append({**label, "predicted": pred, "ground_truth": gt})
        if gt == "sung" and pred == "sung":
            confusion["tp"] += 1
        elif gt == "sung" and pred == "spoken":
            confusion["fn"] += 1
        elif gt == "spoken" and pred == "sung":
            confusion["fp"] += 1
        else:
            confusion["tn"] += 1

    f1 = _f1(confusion["tp"], confusion["fp"], confusion["fn"])
    sung_recall = (
        confusion["tp"] / (confusion["tp"] + confusion["fn"])
        if (confusion["tp"] + confusion["fn"]) > 0
        else 0.0
    )
    return {
        "name": name,
        "confusion": confusion,
        "f1_sung": f1,
        "sung_recall": round(sung_recall, 4),
        "errors": errors,
        "per_label": per_label_results,
    }


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    labels = _load_labels()
    if not labels:
        print(
            f"[validate_sung_classifier] no labels found under {LESSONS_DIR}; "
            f"populate _calibration/lessons/*/region_labels.json or "
            f"_calibration/region_labels.json (see _calibration/README.md)."
        )
        return 1

    print(f"[validate_sung_classifier] evaluating {len(labels)} labeled windows...")
    results = [
        _evaluate("pyworld_regionizer", classifier_a_pyworld, labels),
        _evaluate("zcr_rms_hybrid", classifier_b_zcr_rms, labels),
    ]
    winner = max(results, key=lambda r: r["f1_sung"])

    if winner["f1_sung"] >= 0.8:
        verdict = "ready"
        decision = (
            f"Use {winner['name']} as the Phase 3 sung-region branch trigger "
            f"(F1={winner['f1_sung']}, recall={winner['sung_recall']})."
        )
    else:
        verdict = "kill-condition-candidate"
        decision = (
            f"Both classifiers scored F1 < 0.8 on the held-out set. Per the plan, "
            f"this is a Phase 1 kill-condition candidate — escalate before "
            f"writing Phase 3 code. Best classifier so far: {winner['name']} "
            f"@ F1={winner['f1_sung']}."
        )

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    report_path = REPORTS_DIR / f"sung_classifier_{stamp}.json"
    report_path.write_text(
        json.dumps(
            {
                "timestamp_utc": stamp,
                "n_labels": len(labels),
                "results": results,
                "winner": winner["name"],
                "verdict": verdict,
                "decision": decision,
            },
            indent=2,
        )
    )
    print(f"[validate_sung_classifier] wrote {report_path.relative_to(PROJECT_ROOT)}")
    print(f"[validate_sung_classifier] verdict: {verdict} — {decision}")
    return 0 if verdict == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
