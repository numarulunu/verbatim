"""Phase 1 regression gates.

Runs under `pytest -m benchmark`. Three kinds of checks:

1. MUST-PASS: per-clip WDER in the latest scorecard vs the pinned baseline.
2. WARN: logs clips over `warn_threshold` but does not fail.
3. KILL-SWITCH: `scores/KILL_SWITCH.md` must not exist (baseline run wrote it
   if median DER breached the 0.25 ceiling).

Skipped automatically when the relevant scorecard files do not exist yet
(e.g. before sub-phase 1E has labeled clips).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCORES_DIR = REPO_ROOT / "scores"
BASELINE = SCORES_DIR / "baseline_v0.2.0.json"
KILL_SWITCH = SCORES_DIR / "KILL_SWITCH.md"
WARN_WDER_THRESHOLD = 0.40

pytestmark = pytest.mark.benchmark


def _newest_post_baseline_scorecard() -> Path | None:
    if not SCORES_DIR.exists():
        return None
    candidates = [
        p for p in SCORES_DIR.glob("v*.json")
        if p.name != BASELINE.name and p.name.startswith("v")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_kill_switch_absent():
    """Baseline may not produce a KILL_SWITCH.md. If it does, the cut-
    diarization decision needs a human read — test fails loud."""
    if not KILL_SWITCH.exists():
        return
    pytest.fail(
        "scores/KILL_SWITCH.md exists — baseline median DER breached the cut-"
        "diarization threshold. Read the file, decide, then delete it. "
        f"Contents:\n\n{KILL_SWITCH.read_text(encoding='utf-8')}"
    )


def test_baseline_pinned_once_available():
    """Soft guard: once a baseline is pinned, assert schema basics so a
    corrupted pin is caught before anyone runs gates against it."""
    if not BASELINE.exists():
        pytest.skip("baseline scorecard not pinned yet — run sub-phase 1F")
    payload = _load(BASELINE)
    for field in ("composite", "clips", "version", "label"):
        assert field in payload, f"baseline missing field: {field}"
    assert payload.get("label") == "baseline", "pinned baseline must carry label=baseline"


def test_latest_scorecard_within_tolerance():
    """MUST-PASS: every clip in the newest post-baseline scorecard meets
    `wder_new <= wder_baseline + 0.02` OR `wder_new <= wder_baseline * 1.05`."""
    if not BASELINE.exists():
        pytest.skip("baseline not pinned yet")
    latest = _newest_post_baseline_scorecard()
    if latest is None:
        pytest.skip("no post-baseline scorecard to gate")

    baseline_clips = {c["id"]: c for c in _load(BASELINE).get("clips", [])}
    latest_payload = _load(latest)
    breaches: list[str] = []
    for clip in latest_payload.get("clips", []):
        if clip.get("wder") is None:
            continue
        base = baseline_clips.get(clip["id"])
        if not base or base.get("wder") is None:
            continue
        b = float(base["wder"])
        n = float(clip["wder"])
        if n > b + 0.02 and n > b * 1.05:
            breaches.append(f"{clip['id']}: wder {n:.3f} > baseline {b:.3f} (+tolerance)")

    assert not breaches, (
        "Phase 1 MUST-PASS regression gate tripped:\n  " + "\n  ".join(breaches)
    )


def test_warnings_are_logged(capsys):
    """TRACK metric: any clip over WARN_WDER_THRESHOLD gets logged. This test
    only records and never fails, so a single bad clip doesn't block a merge
    but also doesn't disappear silently."""
    latest = _newest_post_baseline_scorecard() or (BASELINE if BASELINE.exists() else None)
    if latest is None:
        pytest.skip("no scorecard to inspect")
    payload = _load(latest)
    warned = [
        c for c in payload.get("clips", [])
        if c.get("wder") is not None and c["wder"] > WARN_WDER_THRESHOLD
    ]
    for clip in warned:
        print(f"[bench gate] WARN {clip['id']} wder={clip['wder']:.3f} > {WARN_WDER_THRESHOLD}")
    # Pure observational — no assertion.
