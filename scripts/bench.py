"""Diarization regression harness (Phase 1).

Reads a benchmark manifest v2, scores each clip against its reference, writes
a scorecard JSON + appends a composite row to `scores/history.csv`. If
`--baseline` is given, also computes per-clip WDER deltas and exits non-zero
under `--ci` when any clip breaches the MUST-PASS gate.

Scoring is *offline*: we read pre-computed `.whisper.json` sidecars from
`--hyp-dir` (or a path next to each manifest item). We do NOT re-run Whisper
or diarization here — that's the pipeline's job. This keeps the harness
fast, deterministic, and decoupled from the in-flight pipeline refactor.

Per-clip hypothesis is located in this order:
1. `<hyp_dir>/<clip_id>.whisper.json` (when `--hyp-dir` is passed)
2. `<manifest_dir>/hypotheses/<clip_id>.whisper.json`

Missing hypotheses are recorded with a null scorecard entry and a warning —
they do NOT fail the run on their own, so a partial baseline can be
captured before all 10 clips are labeled. The `--require-all` flag promotes
missing-hyp to an error.

Kill-switch: if `--label baseline` and `median_der > --kill-threshold`, the
harness writes `scores/KILL_SWITCH.md` with the composite snapshot. The
`test_bench_gates` pytest integration reads that file.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import random
import statistics
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.diar_metrics import (  # noqa: E402
    cpwer,
    der,
    load_hyp_from_whisper_json,
    load_ref_from_json,
    speaker_purity,
    wder_decomposed,
)
from core.file_hasher import compute_sidecar_hash  # noqa: E402


@dataclass
class ClipScore:
    id: str
    stratum: str
    duration_sec: float
    wder: float | None
    wder_asr: float | None
    wder_assignment: float | None
    cpwer: float | None
    purity: float | None
    der: float | None
    collar_sec: float
    hyp_hash: str | None
    ref_hash: str | None
    skipped_reason: str | None = None


def _seed_all(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np  # noqa: F401
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False, cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        return out.stdout.strip() or "unknown"
    except (FileNotFoundError, OSError):
        return "unknown"


def _locate_hypothesis(clip_id: str, manifest_dir: Path, hyp_dir: Path | None) -> Path | None:
    candidates = []
    if hyp_dir is not None:
        candidates.append(hyp_dir / f"{clip_id}.whisper.json")
    candidates.append(manifest_dir / "hypotheses" / f"{clip_id}.whisper.json")
    for c in candidates:
        if c.exists():
            return c
    return None


def _median(values: list[float]) -> float:
    clean = [v for v in values if v is not None]
    if not clean:
        return 0.0
    return statistics.median(clean)


def _score_clip(
    item: dict,
    manifest_dir: Path,
    hyp_dir: Path | None,
    collar: float,
    require_all: bool,
    skip_der: bool,
) -> ClipScore:
    clip_id = item["id"]
    stratum = item.get("stratum") or item.get("bucket") or "unknown"
    ref_path = manifest_dir / item["reference"]
    hyp_path = _locate_hypothesis(clip_id, manifest_dir, hyp_dir)

    base = ClipScore(
        id=clip_id,
        stratum=stratum,
        duration_sec=0.0,
        wder=None,
        wder_asr=None,
        wder_assignment=None,
        cpwer=None,
        purity=None,
        der=None,
        collar_sec=collar,
        hyp_hash=None,
        ref_hash=None,
    )

    if not ref_path.exists():
        msg = f"reference missing: {ref_path}"
        if require_all:
            raise FileNotFoundError(msg)
        base.skipped_reason = "reference_missing"
        return base
    if hyp_path is None:
        if require_all:
            raise FileNotFoundError(f"hypothesis missing for {clip_id}")
        base.skipped_reason = "hypothesis_missing"
        base.ref_hash = compute_sidecar_hash(ref_path)
        return base

    ref = load_ref_from_json(ref_path)
    hyp = load_hyp_from_whisper_json(hyp_path)

    base.hyp_hash = compute_sidecar_hash(hyp_path)
    base.ref_hash = compute_sidecar_hash(ref_path)
    base.duration_sec = max(
        (w.end for w in ref.words), default=max((t.end for t in ref.turns), default=0.0)
    )

    if not ref.words:
        base.skipped_reason = "reference_has_no_words"
        return base

    w = wder_decomposed(ref.words, hyp.words, collar=collar)
    base.wder = round(w.total, 6)
    base.wder_asr = round(w.asr_component, 6)
    base.wder_assignment = round(w.assignment_component, 6)

    base.cpwer = round(cpwer(ref.words, hyp.words), 6)
    base.purity = round(speaker_purity(ref.turns, hyp.turns), 6)

    if not skip_der:
        try:
            base.der = round(der(ref.turns, hyp.turns, collar=collar * 2), 6)
        except RuntimeError as e:
            print(f"[bench] DER unavailable for {clip_id}: {e}", file=sys.stderr)
            base.der = None

    return base


def _composite(scores: list[ClipScore]) -> dict[str, Any]:
    scored = [s for s in scores if s.skipped_reason is None]
    wders = [s.wder for s in scored if s.wder is not None]
    return {
        "median_wder": round(_median(wders), 6),
        "median_wder_asr": round(_median([s.wder_asr for s in scored if s.wder_asr is not None]), 6),
        "median_wder_assignment": round(_median([s.wder_assignment for s in scored if s.wder_assignment is not None]), 6),
        "median_cpwer": round(_median([s.cpwer for s in scored if s.cpwer is not None]), 6),
        "median_purity": round(_median([s.purity for s in scored if s.purity is not None]), 6),
        "median_der": round(_median([s.der for s in scored if s.der is not None]), 6),
        "max_clip_wder": round(max(wders), 6) if wders else 0.0,
        "n_clips": len(scored),
        "n_skipped": len(scores) - len(scored),
    }


def _write_scorecard(
    path: Path,
    version: str,
    commit: str,
    seed: int,
    label: str,
    composite: dict[str, Any],
    clips: list[ClipScore],
    collar: float,
) -> None:
    payload = {
        "version": version,
        "commit": commit,
        "seed": seed,
        "label": label,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "collar_sec": collar,
        "composite": composite,
        "clips": [asdict(c) for c in clips],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_history(history_path: Path, row: dict[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "timestamp", "commit", "version", "seed", "label", "n_clips",
        "median_wder", "median_wder_asr", "median_wder_assignment",
        "median_cpwer", "median_purity", "median_der", "max_clip_wder",
    ]
    write_header = not history_path.exists() or history_path.stat().st_size == 0
    with history_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _apply_gates(
    clips: list[ClipScore],
    baseline: dict[str, Any] | None,
    warn_threshold: float,
) -> list[str]:
    """Return human-readable gate messages. Non-empty = MUST-PASS breach."""
    breaches: list[str] = []
    if baseline is None:
        return breaches

    baseline_by_id = {c["id"]: c for c in baseline.get("clips", [])}
    for clip in clips:
        if clip.wder is None:
            continue
        base = baseline_by_id.get(clip.id)
        if not base or base.get("wder") is None:
            continue
        b = float(base["wder"])
        ok = clip.wder <= b + 0.02 or clip.wder <= b * 1.05
        if not ok:
            breaches.append(
                f"MUST-PASS: {clip.id} wder {clip.wder:.3f} > baseline {b:.3f} + tolerance"
            )
        if clip.wder > warn_threshold:
            print(f"[bench] WARN: {clip.id} wder {clip.wder:.3f} > {warn_threshold}", file=sys.stderr)
    return breaches


def _maybe_kill_switch(
    scores_dir: Path, label: str, composite: dict[str, Any], threshold: float
) -> Path | None:
    if label != "baseline":
        return None
    median_der = composite.get("median_der", 0.0)
    if median_der <= threshold:
        return None
    path = scores_dir / "KILL_SWITCH.md"
    lines = [
        "# Kill-Condition Triggered",
        "",
        f"Baseline run produced median DER = {median_der:.3f}, above the {threshold:.2f} ceiling.",
        "Per the 2026-04-18 mastermind report, this fires the cut-diarization branch:",
        "surface speaker-separated transcripts as a non-default, user-opt-in mode,",
        "and redirect Phase 2+ effort toward whichever feature beats baseline utility.",
        "",
        "## Composite",
        "```json",
        json.dumps(composite, indent=2),
        "```",
        "",
        "This file is written automatically. Review it, decide, then delete (or pin",
        "the decision in docs) — do NOT ignore it.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 1 diarization regression harness")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="Scorecard JSON output path")
    parser.add_argument("--hyp-dir", type=Path, default=None, help="Directory with <clip_id>.whisper.json files")
    parser.add_argument("--baseline", type=Path, default=None, help="Baseline scorecard for delta gating")
    parser.add_argument("--label", default="ad-hoc")
    parser.add_argument("--version", default="0.2.0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--collar", type=float, default=0.25)
    parser.add_argument("--ci", action="store_true", help="Exit non-zero on MUST-PASS breach")
    parser.add_argument("--require-all", action="store_true", help="Fail if any hyp/ref is missing")
    parser.add_argument("--skip-der", action="store_true", help="Skip pyannote.metrics DER (no optional dep)")
    parser.add_argument("--warn-threshold", type=float, default=0.40)
    parser.add_argument("--kill-threshold", type=float, default=0.25)
    parser.add_argument("--history", type=Path, default=Path("scores/history.csv"))
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(f"manifest missing: {args.manifest}", file=sys.stderr)
        return 2

    _seed_all(args.seed)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_dir = args.manifest.parent

    clips: list[ClipScore] = []
    for item in manifest.get("items", []):
        try:
            score = _score_clip(
                item, manifest_dir, args.hyp_dir, args.collar, args.require_all, args.skip_der,
            )
        except FileNotFoundError as e:
            print(f"[bench] fatal: {e}", file=sys.stderr)
            return 3
        clips.append(score)

    composite = _composite(clips)
    commit = _git_commit()
    _write_scorecard(
        args.out, args.version, commit, args.seed, args.label, composite, clips, args.collar,
    )

    history_row = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "version": args.version,
        "seed": args.seed,
        "label": args.label,
        **composite,
    }
    _append_history(args.history, history_row)

    print(f"[bench] scorecard ->{args.out}")
    for key in ("median_wder", "median_wder_asr", "median_wder_assignment", "median_der", "median_purity"):
        print(f"  {key}: {composite.get(key)}")
    print(f"  n_clips: {composite['n_clips']} (skipped: {composite['n_skipped']})")

    baseline = None
    if args.baseline and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    elif args.baseline:
        print(f"[bench] baseline not found at {args.baseline}", file=sys.stderr)

    breaches = _apply_gates(clips, baseline, args.warn_threshold)
    for msg in breaches:
        print(f"[bench] {msg}", file=sys.stderr)

    scores_dir = args.out.parent
    killed = _maybe_kill_switch(scores_dir, args.label, composite, args.kill_threshold)
    if killed:
        print(f"[bench] KILL-SWITCH written ->{killed}", file=sys.stderr)

    if args.ci and breaches:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
