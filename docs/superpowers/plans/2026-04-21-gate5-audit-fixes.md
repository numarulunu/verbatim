# Gate 5 Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the 8 HIGH-impact fixes SMAC surfaced after Gate 5 patches so the pipeline is correct + resumable before the 320h backlog run.

**Architecture:** Each fix is independent and touches a different module. TDD throughout — failing test first, minimal fix, passing test, commit. Mocks used heavily for the ML-heavy paths (embedder, pyannote) to keep tests runnable without GPU.

**Tech Stack:** Python 3.11, pytest, numpy, soundfile, pyannote.audio 3.3.2, faster-whisper, `utils.atomic_write` helper, `utils.checkpoint` helper.

**Source:** `docs/smac-reports/2026-04-21-concurrency-resumability-bugs.md` (audit). `_backlog.md` (tracking). This plan covers Findings #1–#8 by rank.

**Sequence rationale:**
- Task 1 (requirements) unblocks fresh-machine installs — prerequisite for CI-style test runs.
- Tasks 2, 3, 4 (atomicity / redo / reconciler) protect data integrity — no point running the backlog without these.
- Tasks 5, 6, 7, 8 (attribution math) fix bugs that silently degrade output quality.

---

## File Structure

**New files:**
- `utils/hf_compat.py` — houses `patch_hf_hub_use_auth_token` so it's callable from both `load_diarizer` and `load_embedder` without circular imports.
- `utils/atomic_audio.py` — `atomic_write_wav` helper.
- `tests/test_atomic_audio.py`
- `tests/test_stage3_redo_no_double_count.py`
- `tests/test_corpus_reconcile.py`
- `tests/test_regionizer_frame_period.py`
- `tests/test_bootstrap_trust_counter.py`
- `tests/test_stage3_silent_skip_guard.py`
- `tests/test_embedder_hf_patch.py`

**Modified files:**
- `requirements.txt` (Task 1)
- `stage1_isolate.py` (Task 2)
- `stage3_postprocess.py` (Tasks 3, 7)
- `persons/redo.py` + `run.py` (Task 3)
- `run.py` (Task 4) — preflight reconciler call
- `persons/corpus.py` (Task 4) — add `reconcile_from_polished`
- `persons/regionizer.py` (Task 5)
- `persons/schema.py` + `persons/registry.py` + `stage3_postprocess.py` (Task 6)
- `persons/embedder.py` + `stage2_transcribe_diarize.py` (Task 8) — wire to `utils.hf_compat`

---

## Task 1: Pin NVIDIA runtime deps in requirements.txt

**Rationale:** Gate 5 installed `nvidia-cublas-cu12`, `nvidia-cuda-runtime-cu12`, `nvidia-cudnn-cu11<9`, `speechbrain<1.0` ad-hoc. They aren't pinned. Fresh machine install of `pip install -r requirements.txt` breaks at stage 2 with "Could not locate cudnn_ops_infer64_8.dll".

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Inspect the current requirements.txt**

Run: `cat requirements.txt`
Verify `nvidia-cublas-cu12`, `nvidia-cuda-runtime-cu12`, `nvidia-cudnn-cu11`, `speechbrain<1.0` are ALL absent.

- [ ] **Step 2: Write a smoke-test script that verifies the pins exist**

Create `tests/test_requirements_pins.py`:

```python
"""
Guard: requirements.txt must pin every runtime dep Gate 5 discovered.

Without these pins, a fresh machine install will break at stage 2 (cuDNN
DLL missing). See docs/smac-reports/2026-04-21-*.md Finding #3.
"""
from pathlib import Path

REQUIRED_PINS = (
    "nvidia-cuda-runtime-cu12",
    "nvidia-cublas-cu12",
    "nvidia-cudnn-cu11",
    "speechbrain",
)


def test_requirements_contains_gate5_pins():
    text = Path(__file__).resolve().parent.parent.joinpath("requirements.txt").read_text(encoding="utf-8")
    missing = [p for p in REQUIRED_PINS if p not in text]
    assert not missing, f"requirements.txt is missing Gate-5 pins: {missing}"


def test_speechbrain_pinned_below_1_0():
    text = Path(__file__).resolve().parent.parent.joinpath("requirements.txt").read_text(encoding="utf-8")
    assert "speechbrain" in text
    assert "speechbrain<1.0" in text or 'speechbrain<"1.0"' in text or "speechbrain~=0.5" in text, (
        "speechbrain must be pinned <1.0 — 1.x lazy-imports k2_fsa which crashes under "
        "pytorch-lightning stack walks. See SMAC Finding #3."
    )


def test_cudnn_pinned_to_8_x():
    text = Path(__file__).resolve().parent.parent.joinpath("requirements.txt").read_text(encoding="utf-8")
    # CTranslate2 4.x needs cuDNN 8 specifically
    assert "nvidia-cudnn-cu11<9" in text or "nvidia-cudnn-cu11==8" in text
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_requirements_pins.py -v`
Expected: 3 tests FAIL with `AssertionError: requirements.txt is missing Gate-5 pins: [...]`.

- [ ] **Step 4: Add the pins to requirements.txt**

Modify `requirements.txt` — append this section before the `# --- Test ---` line:

```
# --- Windows GPU runtime (CTranslate2 needs CUDA 12 cuBLAS + cuDNN 8) ---
nvidia-cuda-runtime-cu12
nvidia-cublas-cu12
nvidia-cudnn-cu11<9

# --- pyannote embedder backend (1.x breaks under pytorch-lightning stack walk) ---
speechbrain<1.0
```

- [ ] **Step 5: Re-run the test and commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_requirements_pins.py -v`
Expected: 3 PASS.

```bash
git add requirements.txt tests/test_requirements_pins.py
git commit -m "fix(req): pin nvidia-cublas-cu12, cuda-runtime-cu12, cudnn-cu11<9, speechbrain<1.0"
```

---

## Task 2: Atomic acapella write

**Rationale:** `stage1_isolate._apply_post_gate` calls `sf.write(target, ...)` non-atomically. A crash mid-write leaves a corrupt WAV. `needs_processing()` only checks polished JSON, so corrupt acapella is reused forever. SMAC Finding #1.

**Files:**
- Create: `utils/atomic_audio.py`
- Create: `tests/test_atomic_audio.py`
- Modify: `stage1_isolate.py:108-117`

- [ ] **Step 1: Write the failing test**

Create `tests/test_atomic_audio.py`:

```python
"""
atomic_write_wav must be crash-safe: a simulated failure mid-write must
leave the target untouched (never half-written).
"""
import numpy as np
import pytest
import soundfile as sf
from pathlib import Path


def test_atomic_write_wav_leaves_tmp_on_crash(tmp_path, monkeypatch):
    from utils.atomic_audio import atomic_write_wav

    target = tmp_path / "out.wav"
    # Pre-populate target with known-good content.
    good = np.ones(16000, dtype=np.float32)
    sf.write(str(target), good, 16000, subtype="PCM_16")

    # Patch os.replace to raise — simulates crash between write and rename.
    import os
    original_replace = os.replace

    def boom(src, dst):
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)

    new = np.zeros(16000, dtype=np.float32)
    with pytest.raises(OSError, match="simulated crash"):
        atomic_write_wav(target, new, sr=16000)

    # Target MUST still hold the original content (not corrupted / zeroed).
    restore = sf.read(str(target), dtype="float32")[0]
    assert np.allclose(restore, good), "target was overwritten on a crashed atomic_write"


def test_atomic_write_wav_happy_path(tmp_path):
    from utils.atomic_audio import atomic_write_wav

    target = tmp_path / "out.wav"
    audio = np.linspace(-1, 1, 8000, dtype=np.float32)
    atomic_write_wav(target, audio, sr=16000)

    assert target.exists()
    assert not (tmp_path / "out.wav.tmp").exists(), "tmp sibling must be removed after success"
    readback, sr = sf.read(str(target), dtype="float32")
    assert sr == 16000
    assert readback.shape == audio.shape
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_atomic_audio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.atomic_audio'`.

- [ ] **Step 3: Implement atomic_write_wav**

Create `utils/atomic_audio.py`:

```python
"""
Atomic soundfile write.

Same pattern as utils.atomic_write but for WAV: write to <path>.tmp with
soundfile, fsync, os.replace into place. A crash between the write and the
rename leaves the original <path> untouched (soundfile writes to the .tmp
only — never to the real path).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import soundfile as sf


def atomic_write_wav(
    path: Path,
    audio: np.ndarray,
    sr: int,
    subtype: str = "PCM_16",
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        sf.write(str(tmp), audio, sr, subtype=subtype)
        # soundfile doesn't expose fsync; soundfile closes on context-exit.
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_atomic_audio.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Wire stage1_isolate._apply_post_gate to use atomic_write_wav**

Replace `stage1_isolate.py:108-117` (the `_apply_post_gate` function body):

```python
def _apply_post_gate(acapella: Path) -> None:
    """Apply the SPECTRAL_GATE_DB cleanup in place, atomically."""
    import numpy as np
    import soundfile as sf

    from utils.atomic_audio import atomic_write_wav

    audio, sr = sf.read(str(acapella), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.float32)
    gated = spectral_gate(audio, sr=sr, floor_db=SPECTRAL_GATE_DB)
    atomic_write_wav(acapella, gated, sr)
```

- [ ] **Step 6: Run stage1 compile + existing tests**

Run: `.venv/Scripts/python.exe -m py_compile stage1_isolate.py utils/atomic_audio.py`
Expected: no output (success).

Run: `.venv/Scripts/python.exe -m pytest tests/test_atomic_audio.py -v`
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add utils/atomic_audio.py tests/test_atomic_audio.py stage1_isolate.py
git commit -m "fix(stage1): atomic acapella write — .tmp + os.replace, crash-safe"
```

---

## Task 3: Redo mode must not double-count sessions or re-blend audio

**Rationale:** `--redo` on an already-processed file runs `_update_one_person` a second time. `n_prior` is 1 (from the first pass), so `blended = (original_centroid * 1 + same_audio_centroid) / 2` averages the same audio twice. Session counters also increment twice. SMAC Finding #2.

**Files:**
- Create: `tests/test_stage3_redo_no_double_count.py`
- Modify: `stage3_postprocess.py` — `update_voice_libraries`, `_update_one_person` signatures
- Modify: `run.py:_finalize` — pass `is_redo`
- Modify: `run.py:_redo_one` — pass `is_redo=True`

- [ ] **Step 1: Write the failing test**

Create `tests/test_stage3_redo_no_double_count.py`:

```python
"""
Redo must not double-count sessions or re-blend audio.

Simulated scenario: process a person once (is_redo=False), then process the
same session again (is_redo=True). After the redo, neither the centroid nor
session counts should have changed relative to the first-pass result.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest


@pytest.fixture
def tmp_voiceprint_root(monkeypatch, tmp_path):
    monkeypatch.setenv("VOCALITY_ROOT", str(tmp_path))
    # Force the config module to re-evaluate PROJECT_ROOT.
    sys.modules.pop("config", None)
    for mod in list(sys.modules):
        if mod.startswith("persons.") or mod.startswith("stage3"):
            sys.modules.pop(mod, None)
    yield tmp_path


def _fake_embed(audio):
    # Deterministic fake: returns a normalized vector seeded from len(audio).
    rng = np.random.RandomState(len(audio) % 10_000)
    vec = rng.randn(512).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-9)


def test_redo_does_not_double_count(tmp_voiceprint_root, monkeypatch):
    """Running update_voice_libraries twice with is_redo=True the second time
    must leave centroid + session counters as they were after first pass."""
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry, schema
    from stage3_postprocess import update_voice_libraries

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    meta = SessionMeta(
        date="2025-08-07", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("test.mp4"),
    )

    # Pre-register vasquez so identify_speakers isn't exercised in this test.
    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen=meta.date,
    )

    # Build a single 20s (>VOICE_LIB_MIN_REGION_SECONDS) segment attributed to vasquez.
    audio = np.ones(16000 * 30, dtype=np.float32)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 1.0,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    # First pass (normal).
    update_voice_libraries(segments, label_to_person, audio, 16000, meta, is_redo=False)
    rec1 = registry.load("vasquez")
    centroid1 = np.load(
        tmp_voiceprint_root / "_voiceprints" / "people" / "vasquez" / "speaking.npy"
    )

    # Redo pass — same inputs, is_redo=True.
    update_voice_libraries(segments, label_to_person, audio, 16000, meta, is_redo=True)
    rec2 = registry.load("vasquez")
    centroid2 = np.load(
        tmp_voiceprint_root / "_voiceprints" / "people" / "vasquez" / "speaking.npy"
    )

    # Session counts unchanged.
    assert rec1.n_sessions_as_teacher == rec2.n_sessions_as_teacher == 1
    assert rec1.region_session_counts == rec2.region_session_counts

    # Centroid unchanged.
    assert np.allclose(centroid1, centroid2), "redo must not re-blend the same audio"


def test_redo_flag_defaults_to_false(tmp_voiceprint_root, monkeypatch):
    """Existing callers that don't pass is_redo must still default to the
    normal-run behavior (update applied)."""
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import update_voice_libraries

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    meta = SessionMeta(
        date="2025-08-07", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("test.mp4"),
    )
    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen=meta.date,
    )
    audio = np.ones(16000 * 30, dtype=np.float32)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 1.0,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    # Call without is_redo — must behave as is_redo=False.
    update_voice_libraries(segments, label_to_person, audio, 16000, meta)
    assert registry.load("vasquez").n_sessions_as_teacher == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stage3_redo_no_double_count.py -v`
Expected: first test FAILS with `TypeError: update_voice_libraries() got an unexpected keyword argument 'is_redo'` (since the param doesn't exist yet).

- [ ] **Step 3: Add `is_redo` parameter and gate the double-count writes**

Modify `stage3_postprocess.py`. Change the `update_voice_libraries` signature and pass-through:

```python
def update_voice_libraries(
    segments: list[dict],
    label_to_person: dict[str, PersonRecord],
    acapella: "np.ndarray",
    sr: int,
    meta: "SessionMeta",
    is_redo: bool = False,
) -> None:
```

At the end of the `for pid, region_clips in per_person_regions.items():` loop body, change the call to `_update_one_person` from:

```python
        _update_one_person(person, region_clips, per_person_durations[pid], meta)
```

to:

```python
        _update_one_person(person, region_clips, per_person_durations[pid], meta, is_redo=is_redo)
```

Change `_update_one_person`'s signature:

```python
def _update_one_person(
    person: PersonRecord,
    region_clips: dict[str, list[np.ndarray]],
    total_duration_s: float,
    meta: "SessionMeta",
    is_redo: bool = False,
) -> None:
```

Inside `_update_one_person`, wrap the running-mean blend + the counter block in redo-aware guards.

Replace the existing per-region loop body at `stage3_postprocess.py:319-339` with:

```python
    # Per-region running-mean.
    active_centroids: list[np.ndarray] = []
    from config import DECODE_SAMPLE_RATE
    for region, clips in region_clips.items():
        concat = np.concatenate(clips).astype(np.float32)
        if len(concat) / DECODE_SAMPLE_RATE < VOICE_LIB_MIN_REGION_SECONDS:
            continue
        new_centroid = embed(concat)
        existing_path = pdir / f"{region}.npy"
        if is_redo and existing_path.exists():
            # Redo: this session's audio is ALREADY folded into the existing
            # centroid. Re-blending would double-weight it. Keep the prior
            # value and only re-derive `active_centroids` for the universal
            # rollup below.
            blended = np.load(existing_path)
        elif existing_path.exists():
            prior = np.load(existing_path)
            n_prior = person.region_session_counts.get(region, 0)
            blended = (prior * n_prior + new_centroid) / (n_prior + 1)
            blended = blended / (np.linalg.norm(blended) + 1e-9)
            # Drift warning
            drift = 1.0 - float(np.dot(prior, blended) / (np.linalg.norm(prior) * np.linalg.norm(blended) + 1e-9))
            if drift > DRIFT_WARNING_THRESHOLD:
                log.warning("drift for %s.%s: %.3f > %.3f", person.id, region, drift, DRIFT_WARNING_THRESHOLD)
        else:
            blended = new_centroid
        if not is_redo:
            np.save(existing_path, blended)
            person.region_session_counts[region] = person.region_session_counts.get(region, 0) + 1
            if region not in person.observed_regions:
                person.observed_regions.append(region)
            updated_regions.append(region)
        if region in REGION_LABELS:
            active_centroids.append(blended)
```

Replace the post-loop counter block at `stage3_postprocess.py:348-357` with:

```python
    if not is_redo:
        # Role + session counts.
        if meta.teacher_id == person.id:
            person.n_sessions_as_teacher += 1
        elif meta.student_id == person.id:
            person.n_sessions_as_student += 1
        person.total_hours += total_duration_s / 3600.0
        person.last_updated = meta.date
        if person.first_seen is None:
            person.first_seen = meta.date
        registry.save(person)
    log.info(
        "updated voice library for %r: regions=%s sessions=%d redo=%s",
        person.id, updated_regions, total_sessions(person), is_redo,
    )
```

- [ ] **Step 4: Wire `is_redo=True` through `run.py._redo_one`**

In `run.py._redo_one` function, find the call `st3.update_voice_libraries(polished, label_to_person, audio, 16000, meta)` and replace with:

```python
    st3.update_voice_libraries(polished, label_to_person, audio, 16000, meta, is_redo=True)
```

In `run.py._finalize`, leave the call as-is (defaults to `is_redo=False`).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stage3_redo_no_double_count.py -v`
Expected: 2 PASS.

Run: `.venv/Scripts/python.exe -m py_compile stage3_postprocess.py run.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add stage3_postprocess.py run.py tests/test_stage3_redo_no_double_count.py
git commit -m "fix(redo): skip running-mean blend + session-count increment on redo"
```

---

## Task 4: Corpus-vs-polished reconciler on preflight

**Rationale:** `finalize()` writes the polished JSON first, then updates corpus. If corpus write fails (disk, permissions, lock), the polished JSON is committed and `needs_processing` skips it on next run — but it's missing from `corpus.json`. No reconciler exists. SMAC Finding #4.

**Files:**
- Create: `tests/test_corpus_reconcile.py`
- Modify: `persons/corpus.py` — add `reconcile_from_polished()`
- Modify: `run.py` — call in `preflight()`

- [ ] **Step 1: Write the failing test**

Create `tests/test_corpus_reconcile.py`:

```python
"""
reconcile_from_polished scans POLISHED_DIR for transcripts missing from
corpus.json and replays them. Protects against a crash between the
polished-JSON write and the corpus-update in stage3.finalize.
"""
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    monkeypatch.setenv("VOCALITY_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "config" or mod.startswith("persons."):
            sys.modules.pop(mod, None)
    yield tmp_path


def _mk_polished(dir_path: Path, file_id: str, language: str, duration_s: float,
                 teacher: str, student: str) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{file_id}.json").write_text(
        json.dumps({
            "file_id": file_id,
            "date": file_id.split("_")[0],
            "language": language,
            "duration_s": duration_s,
            "processed_at": "2026-04-21T00:00:00+00:00",
            "pipeline_version": "1.0.0",
            "polish_engine": "cli",
            "overlap_ratio": 0.0,
            "source_codec": "aac",
            "source_bitrate": 128000,
            "mfa_aligned": False,
            "participants": [
                {"id": teacher, "name": teacher, "role": "teacher"},
                {"id": student, "name": student, "role": "student"},
            ],
            "segments": [{"start": 0.0, "end": 1.0, "text": "hi"}],
            "processed_at_db_state": {},
        }, indent=2),
        encoding="utf-8",
    )


def test_reconcile_finds_orphan_polished(tmp_project):
    import config
    from persons import corpus

    _mk_polished(config.POLISHED_DIR, "2025-08-07_vasquez__ionut_en",
                 "en", 600.0, "vasquez", "ionut")

    # corpus.json doesn't exist yet → reconciler should create it with the
    # orphan transcript.
    added = corpus.reconcile_from_polished()

    assert added == 1
    entries = corpus.load()
    assert len(entries) == 1
    assert entries[0]["file_id"] == "2025-08-07_vasquez__ionut_en"
    assert entries[0]["teacher_id"] == "vasquez"
    assert entries[0]["student_id"] == "ionut"


def test_reconcile_skips_already_indexed(tmp_project):
    import config
    from persons import corpus

    _mk_polished(config.POLISHED_DIR, "2025-08-07_vasquez__ionut_en",
                 "en", 600.0, "vasquez", "ionut")

    first = corpus.reconcile_from_polished()
    second = corpus.reconcile_from_polished()

    assert first == 1
    assert second == 0, "second run must be a no-op"
    assert len(corpus.load()) == 1


def test_reconcile_adds_only_missing(tmp_project):
    import config
    from persons import corpus

    _mk_polished(config.POLISHED_DIR, "2025-08-07_vasquez__ionut_en",
                 "en", 600.0, "vasquez", "ionut")
    _mk_polished(config.POLISHED_DIR, "2025-10-06_ionut__luiza_en",
                 "en", 300.0, "ionut", "luiza")

    # Pre-populate corpus with only one entry.
    corpus.append_session({"file_id": "2025-08-07_vasquez__ionut_en",
                            "date": "2025-08-07", "language": "en",
                            "teacher_id": "vasquez", "student_id": "ionut"})

    added = corpus.reconcile_from_polished()
    assert added == 1, "only the luiza entry is missing"
    file_ids = [e["file_id"] for e in corpus.load()]
    assert sorted(file_ids) == [
        "2025-08-07_vasquez__ionut_en",
        "2025-10-06_ionut__luiza_en",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_corpus_reconcile.py -v`
Expected: 3 tests FAIL with `AttributeError: module 'persons.corpus' has no attribute 'reconcile_from_polished'`.

- [ ] **Step 3: Add reconcile_from_polished to persons/corpus.py**

Append to `persons/corpus.py`:

```python
def reconcile_from_polished() -> int:
    """
    Scan POLISHED_DIR for transcripts whose file_id is absent from corpus.json
    and append corpus entries for them. Returns the number of entries added.

    Guards against a crash between stage3.finalize's two writes (polished
    JSON then corpus update). On next startup, run.preflight calls this to
    replay orphan entries before any normal processing.
    """
    import json as _json
    import logging as _logging

    _log = _logging.getLogger(__name__)

    from config import POLISHED_DIR as _POLISHED_DIR

    if not _POLISHED_DIR.exists():
        return 0

    indexed = {e.get("file_id") for e in load() if e.get("file_id")}
    added = 0
    for polished in sorted(_POLISHED_DIR.glob("*.json")):
        file_id = polished.stem
        if file_id in indexed:
            continue
        try:
            with open(polished, "r", encoding="utf-8") as fh:
                transcript = _json.load(fh)
        except (OSError, _json.JSONDecodeError) as exc:
            _log.warning("reconcile: skipping %s (%s)", polished.name, exc)
            continue
        append_session(session_entry_from(transcript))
        added += 1
        _log.info("reconcile: re-indexed orphan polished %s", file_id)
    return added
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_corpus_reconcile.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Call the reconciler from `run.preflight`**

In `run.py:preflight()`, after the `pin_to_p_cores()` call at the bottom, append:

```python
    # Reconcile any orphan polished JSONs missing from corpus.json (crash
    # recovery for the stage3.finalize two-write window — see _backlog.md
    # SMAC Finding #4).
    from persons.corpus import reconcile_from_polished
    added = reconcile_from_polished()
    if added:
        log.warning("corpus reconciler: re-indexed %d orphan polished transcript(s)", added)
```

- [ ] **Step 6: Compile + commit**

Run: `.venv/Scripts/python.exe -m py_compile persons/corpus.py run.py`
Expected: no output.

Run: `.venv/Scripts/python.exe -m pytest tests/test_corpus_reconcile.py -v`
Expected: 3 PASS.

```bash
git add persons/corpus.py run.py tests/test_corpus_reconcile.py
git commit -m "fix(corpus): reconcile orphan polished JSONs on preflight"
```

---

## Task 5: Fix pyworld vs librosa frame-period mismatch

**Rationale:** `regionizer._has_sustained_pitch` hardcodes `frame_s = 512.0 / sr` (librosa hop, 32 ms at 16 kHz). But `config.PITCH_EXTRACTOR` defaults to `"pyworld"` with `frame_period=10.0 ms`. The stability check fires ~3× too early on pyworld output → false-positive `sung_full` classifications. SMAC Finding #5.

**Files:**
- Create: `tests/test_regionizer_frame_period.py`
- Modify: `persons/regionizer.py` — parameterize `frame_s` on extractor

- [ ] **Step 1: Write the failing test**

Create `tests/test_regionizer_frame_period.py`:

```python
"""
_has_sustained_pitch's frame-period must match the extractor (pyworld 10ms
vs librosa ~32ms at sr=16000). Otherwise the SUSTAIN_MIN_SECONDS check
fires at the wrong frame count.
"""
import numpy as np
import pytest


def test_frame_s_is_10ms_for_pyworld(monkeypatch):
    from persons import regionizer

    monkeypatch.setattr(regionizer, "PITCH_EXTRACTOR", "pyworld")

    # 1.5s of stable 440 Hz at pyworld 10ms frames = 150 samples.
    n_frames = 150
    f0 = np.full(n_frames, 440.0, dtype=np.float32)

    # With correct 10ms frame_s, 150 frames × 10ms = 1.5s >= SUSTAIN_MIN_SECONDS.
    # The function MUST detect sustained pitch. If frame_s is stuck at 32ms,
    # it would need 150 frames × 32ms = 4.8s and return False.
    assert regionizer._has_sustained_pitch(f0, frame_s=0.010, min_duration_s=1.5)


def test_frame_s_is_sr_derived_for_librosa(monkeypatch):
    from persons import regionizer

    monkeypatch.setattr(regionizer, "PITCH_EXTRACTOR", "librosa")

    # 1.5s of stable 440 Hz at librosa 32ms frames = ~47 samples.
    n_frames = 47
    f0 = np.full(n_frames, 440.0, dtype=np.float32)

    frame_s = 512.0 / 16000  # 0.032
    assert regionizer._has_sustained_pitch(f0, frame_s=frame_s, min_duration_s=1.5)


def test_classify_segment_uses_correct_frame_period(monkeypatch):
    """classify_segment -> _has_sustained_pitch passes a frame_s that
    matches PITCH_EXTRACTOR, not the hardcoded librosa value."""
    from persons import regionizer

    monkeypatch.setattr(regionizer, "PITCH_EXTRACTOR", "pyworld")

    # Fake pitch extractor returning 150 frames of stable 440 Hz.
    def fake_pitch(audio, sr):
        return np.full(150, 440.0, dtype=np.float32)

    monkeypatch.setattr(regionizer, "extract_pitch", fake_pitch)
    # Use 1.5s of arbitrary audio; pitch extractor mocked out.
    audio = np.zeros(16000 * 2, dtype=np.float32)
    label = regionizer.classify_segment(audio, sr=16000, person=None)
    assert label == "sung_full", f"expected sung_full with 150-frame sustained pitch, got {label}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_regionizer_frame_period.py -v`
Expected: `test_classify_segment_uses_correct_frame_period` FAILS with assertion — classify_segment currently passes the hardcoded `frame_s = 512.0 / sr` so 150-frame pyworld input fails the sustained check.

- [ ] **Step 3: Parameterize `_has_sustained_pitch` signature + fix the caller**

Modify `persons/regionizer.py` `_has_sustained_pitch` signature to take explicit `frame_s`:

```python
def _has_sustained_pitch(
    f0: "np.ndarray",
    frame_s: float,
    min_duration_s: float,
    stability_semitones: float = 0.5,
) -> bool:
```

This signature already exists. Verify at `persons/regionizer.py` around line 246.

Modify `classify_segment` at around `persons/regionizer.py:149` to derive the right frame_s from the extractor. Replace:

```python
    # Sustained-pitch detection — frame_period=10ms for pyworld, 512/sr for librosa.
    frame_s = 512.0 / sr
    if _has_sustained_pitch(f0, frame_s, SUSTAIN_MIN_SECONDS):
        return "sung_full"
```

with:

```python
    # Sustained-pitch detection. Frame period depends on the extractor:
    # pyworld uses a fixed 10ms period (regionizer.extract_pitch sets
    # frame_period=10.0); librosa.pyin uses hop_length/sr.
    if PITCH_EXTRACTOR == "pyworld":
        frame_s = 0.010
    else:
        frame_s = 512.0 / sr
    if _has_sustained_pitch(f0, frame_s, SUSTAIN_MIN_SECONDS):
        return "sung_full"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_regionizer_frame_period.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Compile + commit**

Run: `.venv/Scripts/python.exe -m py_compile persons/regionizer.py`

```bash
git add persons/regionizer.py tests/test_regionizer_frame_period.py
git commit -m "fix(regionizer): derive frame_s from PITCH_EXTRACTOR (pyworld=10ms, librosa=sr-derived)"
```

---

## Task 6: Bootstrap trust counter — enforce the first-3-sessions gate

**Rationale:** Gate 5 set bootstrap confidence to `1.0` to avoid first-session rejection. But `NEW_PERSON_CONFIDENCE_GATE = 0.75` on sessions 2 and 3 is now unreachable — no code tracks "this person is within their first 3 sessions." SMAC Finding #6.

**Files:**
- Create: `tests/test_bootstrap_trust_counter.py`
- Modify: `persons/schema.py` — add `bootstrap_sessions_remaining: int = 3`
- Modify: `persons/registry.py:register_new` — (no change needed; dataclass default handles it)
- Modify: `stage3_postprocess.py:update_voice_libraries` — gate session-2/3 updates behind real confidence check + decrement counter

- [ ] **Step 1: Write the failing test**

Create `tests/test_bootstrap_trust_counter.py`:

```python
"""
First 3 sessions of any new person must require real match confidence > 0.75
or the voice-library update must be rejected (brief §7 + SMAC Finding #6).
Bootstrap session 1 gets a free pass (confidence=1.0 by construction, the
cluster IS this person). Sessions 2 and 3 must check real confidence.
"""
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    monkeypatch.setenv("VOCALITY_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "config" or mod.startswith("persons.") or mod.startswith("stage3"):
            sys.modules.pop(mod, None)
    yield tmp_path


def _fake_embed(audio):
    rng = np.random.RandomState(len(audio) % 10000)
    vec = rng.randn(512).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-9)


def test_register_new_sets_bootstrap_sessions_remaining_to_3(tmp_project):
    import config  # noqa: F401
    from persons import registry

    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    assert person.bootstrap_sessions_remaining == 3


def test_session_2_with_low_confidence_rejected(tmp_project, monkeypatch):
    """After bootstrap, session 2 with real confidence < 0.75 must NOT
    decrement the trust counter or update the voice library."""
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import update_voice_libraries

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    # Simulate that bootstrap session 1 already happened.
    person.bootstrap_sessions_remaining = 2
    person.n_sessions_as_teacher = 1
    registry.save(person)

    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("x.mp4"),
    )
    audio = np.ones(16000 * 30, dtype=np.float32)
    # Session 2: low confidence (0.5 < 0.75 gate)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 0.5,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    update_voice_libraries(segments, label_to_person, audio, 16000, meta)

    after = registry.load("vasquez")
    assert after.bootstrap_sessions_remaining == 2, "counter must NOT decrement on rejected update"
    assert after.n_sessions_as_teacher == 1, "session count must NOT increment on rejected update"


def test_session_2_with_high_confidence_decrements_counter(tmp_project, monkeypatch):
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import update_voice_libraries

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)
    monkeypatch.setattr("persons.matcher.check_collisions", lambda: [])

    person = registry.register_new(
        id_="vasquez", display_name="vasquez",
        default_role="teacher", first_seen="2025-08-07",
    )
    person.bootstrap_sessions_remaining = 2
    person.n_sessions_as_teacher = 1
    # Seed the speaking.npy so the update finds a prior centroid.
    pdir = tmp_project / "_voiceprints" / "people" / "vasquez"
    pdir.mkdir(parents=True, exist_ok=True)
    seed = np.random.RandomState(0).randn(512).astype(np.float32)
    seed = seed / np.linalg.norm(seed)
    np.save(pdir / "speaking.npy", seed)
    person.region_session_counts = {"speaking": 1}
    person.observed_regions = ["speaking"]
    registry.save(person)

    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="vasquez", student_id="ionut",
        source_path=Path("x.mp4"),
    )
    audio = np.ones(16000 * 30, dtype=np.float32)
    segments = [{
        "start": 0.0, "end": 20.0,
        "speaker_id": "vasquez", "speaker_confidence": 0.9,
        "matched_region": "speaking",
    }]
    label_to_person = {"SPEAKER_00": person}

    update_voice_libraries(segments, label_to_person, audio, 16000, meta)

    after = registry.load("vasquez")
    assert after.bootstrap_sessions_remaining == 1
    assert after.n_sessions_as_teacher == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_bootstrap_trust_counter.py -v`
Expected: first test FAILS with `AttributeError: 'PersonRecord' object has no attribute 'bootstrap_sessions_remaining'`.

- [ ] **Step 3: Add `bootstrap_sessions_remaining` to PersonRecord**

Modify `persons/schema.py`. Add a field to the dataclass — after the `collisions: list[str] = field(default_factory=list)` line add:

```python
    bootstrap_sessions_remaining: int = 3
```

Also update `from_dict` defensively — nothing changes since dataclass default handles missing field from older metadata.

- [ ] **Step 4: Gate session-2/3 updates behind real confidence in update_voice_libraries**

In `stage3_postprocess.update_voice_libraries`, replace the existing rejection gate block (around the `avg_conf < UPDATE_REJECTION_THRESHOLD` check) with:

```python
        avg_conf = (
            sum(per_person_confidences.get(pid, [])) / max(1, len(per_person_confidences.get(pid, [])))
        )
        # Hard rejection: below-floor confidence never updates.
        if avg_conf < UPDATE_REJECTION_THRESHOLD:
            log.warning(
                "voice library update rejected for %s: avg confidence %.2f < %.2f",
                pid, avg_conf, UPDATE_REJECTION_THRESHOLD,
            )
            continue
        person = label_to_person.get(_first_label_for_pid(pid, label_to_person)) or _load_or_none(pid)
        if person is None:
            continue
        # First-3-sessions poisoning guard (SMAC Finding #6). Bootstrap
        # session passes 1.0 unconditionally (cluster IS this person). After
        # bootstrap, the NEXT 2 sessions require real match confidence above
        # NEW_PERSON_CONFIDENCE_GATE or they're skipped.
        if (
            person.bootstrap_sessions_remaining > 0
            and person.bootstrap_sessions_remaining < 3        # not the bootstrap itself
            and avg_conf < NEW_PERSON_CONFIDENCE_GATE
        ):
            log.warning(
                "first-3-sessions gate: skipping update for %s (avg conf %.2f < %.2f); "
                "run `enroll.py confirm %s <session_id>` to approve manually",
                pid, avg_conf, NEW_PERSON_CONFIDENCE_GATE, pid,
            )
            continue
        _update_one_person(person, region_clips, per_person_durations[pid], meta, is_redo=is_redo)
        # Decrement trust counter (bootstrap counted separately via the
        # bootstrap_new_person path, which starts at 3 and the first real
        # accepted update brings it to 2).
        if person.bootstrap_sessions_remaining > 0 and not is_redo:
            person.bootstrap_sessions_remaining -= 1
            registry.save(person)
```

Also ensure `NEW_PERSON_CONFIDENCE_GATE` is imported at the top of `stage3_postprocess.py`. Check the imports and add if missing:

```python
from config import (
    ...,
    NEW_PERSON_CONFIDENCE_GATE,
    ...,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_bootstrap_trust_counter.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Compile + commit**

Run: `.venv/Scripts/python.exe -m py_compile persons/schema.py stage3_postprocess.py`

```bash
git add persons/schema.py stage3_postprocess.py tests/test_bootstrap_trust_counter.py
git commit -m "fix(persons): per-person bootstrap_sessions_remaining enforces 0.75 gate on sessions 2-3"
```

---

## Task 7: `_update_one_person` must not increment session counts when no centroid was written

**Rationale:** If no region has ≥10s of audio, `active_centroids` is empty — universal.npy / recent.npy are not written. But the session counters (`n_sessions_as_teacher/student`, `total_hours`) still increment, inflating session counts for persons whose voiceprint library wasn't actually updated. After 3 such "empty" sessions, the first-3-sessions gate (Task 6) wrongly reports the person as seasoned. SMAC Finding #7.

**Files:**
- Create: `tests/test_stage3_silent_skip_guard.py`
- Modify: `stage3_postprocess.py:_update_one_person`

- [ ] **Step 1: Write the failing test**

Create `tests/test_stage3_silent_skip_guard.py`:

```python
"""
When a person appears in a session but has no region with at least
VOICE_LIB_MIN_REGION_SECONDS of audio, _update_one_person must NOT
increment session counters or write a stale universal — otherwise the
first-3-sessions gate counts empty appearances against the person.
"""
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    monkeypatch.setenv("VOCALITY_ROOT", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "config" or mod.startswith("persons.") or mod.startswith("stage3"):
            sys.modules.pop(mod, None)
    yield tmp_path


def _fake_embed(audio):
    rng = np.random.RandomState(len(audio) % 10000)
    vec = rng.randn(512).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-9)


def test_empty_region_clips_does_not_increment_counters(tmp_project, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.WARNING)
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import _update_one_person

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)

    person = registry.register_new(
        id_="alessandro", display_name="alessandro",
        default_role="teacher", first_seen="2025-08-07",
    )
    baseline_n_teacher = person.n_sessions_as_teacher
    baseline_total_hours = person.total_hours

    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="alessandro", student_id="ionut",
        source_path=Path("x.mp4"),
    )

    # All clips are under VOICE_LIB_MIN_REGION_SECONDS (<10s each AND <10s total).
    region_clips = {"speaking": [np.zeros(16000 * 5, dtype=np.float32)]}  # 5s only

    _update_one_person(person, region_clips, total_duration_s=5.0, meta=meta, is_redo=False)

    after = registry.load("alessandro")
    assert after.n_sessions_as_teacher == baseline_n_teacher, "no update happened — count must not increment"
    assert after.total_hours == baseline_total_hours
    # Must have logged a visible warning (not silent).
    assert any("empty" in rec.message.lower() or "insufficient" in rec.message.lower() or "skipped" in rec.message.lower()
               for rec in caplog.records), "silent skip — add a warning"


def test_has_region_clips_does_increment(tmp_project, monkeypatch):
    """Baseline: when region_clips does contain enough audio, counters DO increment."""
    import config  # noqa: F401
    from filename_parser import SessionMeta
    from persons import registry
    from stage3_postprocess import _update_one_person

    monkeypatch.setattr("persons.embedder.embed", _fake_embed)

    person = registry.register_new(
        id_="alessandro", display_name="alessandro",
        default_role="teacher", first_seen="2025-08-07",
    )
    meta = SessionMeta(
        date="2025-08-14", language="en",
        teacher_id="alessandro", student_id="ionut",
        source_path=Path("x.mp4"),
    )

    region_clips = {"speaking": [np.zeros(16000 * 30, dtype=np.float32)]}  # 30s
    _update_one_person(person, region_clips, total_duration_s=30.0, meta=meta, is_redo=False)

    after = registry.load("alessandro")
    assert after.n_sessions_as_teacher == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stage3_silent_skip_guard.py -v`
Expected: `test_empty_region_clips_does_not_increment_counters` FAILS — the current code DOES increment counters even when no region had enough audio.

- [ ] **Step 3: Gate the counter increment behind `active_centroids`**

Modify the counter block in `_update_one_person` (this builds on the changes from Task 3). Replace the `if not is_redo: ...counters...` block with:

```python
    if not is_redo:
        if not active_centroids:
            # No region cleared the VOICE_LIB_MIN_REGION_SECONDS bar — the
            # voice library didn't actually change. Don't inflate session
            # counts with empty appearances; flag it so the operator knows.
            log.warning(
                "skipped voice-library update for %r — no region had >=%.1fs of audio "
                "(session counters NOT incremented; person appears in transcript only)",
                person.id, VOICE_LIB_MIN_REGION_SECONDS,
            )
            return
        # Role + session counts.
        if meta.teacher_id == person.id:
            person.n_sessions_as_teacher += 1
        elif meta.student_id == person.id:
            person.n_sessions_as_student += 1
        person.total_hours += total_duration_s / 3600.0
        person.last_updated = meta.date
        if person.first_seen is None:
            person.first_seen = meta.date
        registry.save(person)
    log.info(
        "updated voice library for %r: regions=%s sessions=%d redo=%s",
        person.id, updated_regions, total_sessions(person), is_redo,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stage3_silent_skip_guard.py -v`
Expected: 2 PASS.

Run the regression tests from Task 3 to confirm they still pass:
Run: `.venv/Scripts/python.exe -m pytest tests/test_stage3_redo_no_double_count.py tests/test_bootstrap_trust_counter.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Compile + commit**

Run: `.venv/Scripts/python.exe -m py_compile stage3_postprocess.py`

```bash
git add stage3_postprocess.py tests/test_stage3_silent_skip_guard.py
git commit -m "fix(stage3): don't increment session counts when no region had enough audio"
```

---

## Task 8: `load_embedder` must patch hf_hub before instantiation

**Rationale:** `persons/embedder.py:43` calls `PretrainedSpeakerEmbedding(..., use_auth_token=HF_TOKEN)`. The deprecated `use_auth_token` kwarg was translated by a `_patch_hf_hub_use_auth_token` shim — but that shim is only invoked by `stage2_transcribe_diarize.load_diarizer`. In `--redo` mode, `_redo_one` skips stage 2 entirely → the patch never runs → the first `load_embedder` call in redo crashes with "unexpected keyword argument 'use_auth_token'" on a fresh venv. SMAC Finding #9.

**Files:**
- Create: `utils/hf_compat.py` — extract the patch to a neutral location
- Create: `tests/test_embedder_hf_patch.py`
- Modify: `stage2_transcribe_diarize.py` — replace inline patch with import
- Modify: `persons/embedder.py:load_embedder` — call the patch before instantiation
- Modify: `run.py:preflight` — call the patch proactively

- [ ] **Step 1: Write the failing test**

Create `tests/test_embedder_hf_patch.py`:

```python
"""
load_embedder must ensure huggingface_hub.hf_hub_download accepts the
deprecated `use_auth_token=` kwarg before pyannote is imported. Otherwise
redo-mode runs (which skip stage 2 / load_diarizer) crash with
TypeError: hf_hub_download() got an unexpected keyword argument 'use_auth_token'.
"""
import sys

import pytest


def test_hf_compat_patch_accepts_use_auth_token():
    """The shim must translate use_auth_token= to token= without raising."""
    from utils.hf_compat import patch_hf_hub_use_auth_token
    patch_hf_hub_use_auth_token()

    import huggingface_hub
    # Call the patched hf_hub_download with the deprecated kwarg. We expect
    # any exception OTHER than the TypeError (the shim should have forwarded
    # it as token=). Network errors are fine — they prove the kwarg was
    # accepted.
    try:
        huggingface_hub.hf_hub_download(
            repo_id="hf-internal-testing/tiny-random-gpt2",
            filename="config.json",
            use_auth_token=None,
            local_files_only=True,
        )
    except TypeError as e:
        if "use_auth_token" in str(e):
            pytest.fail(f"shim did not translate kwarg: {e}")
    except Exception:
        # Any other error is fine — kwarg accepted.
        pass


def test_load_embedder_invokes_hf_compat(monkeypatch):
    """load_embedder must call patch_hf_hub_use_auth_token before touching pyannote,
    so redo-mode (which doesn't load the diarizer) still works."""
    called = {"patch": False, "pretrained": False}

    def fake_patch():
        called["patch"] = True

    class FakeEmbedder:
        def __init__(self, *args, **kwargs):
            called["pretrained"] = True
            # Ensure patch ran BEFORE this constructor was called.
            assert called["patch"], "patch must run before PretrainedSpeakerEmbedding"

    # Fake the three imports load_embedder performs.
    import types
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        device=lambda name: f"device({name})",
    )
    fake_pyannote_pipelines = types.SimpleNamespace(
        speaker_verification=types.SimpleNamespace(PretrainedSpeakerEmbedding=FakeEmbedder),
    )

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "pyannote", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pyannote.audio", types.SimpleNamespace())
    monkeypatch.setitem(
        sys.modules, "pyannote.audio.pipelines", types.SimpleNamespace(speaker_verification=fake_pyannote_pipelines.speaker_verification)
    )
    monkeypatch.setitem(
        sys.modules,
        "pyannote.audio.pipelines.speaker_verification",
        fake_pyannote_pipelines.speaker_verification,
    )

    # Reload embedder fresh so _model singleton is cleared.
    sys.modules.pop("persons.embedder", None)
    sys.modules.pop("utils.hf_compat", None)

    # Install a fake hf_compat with our spy patch.
    fake_hf_compat = types.SimpleNamespace(
        patch_hf_hub_use_auth_token=fake_patch,
    )
    monkeypatch.setitem(sys.modules, "utils.hf_compat", fake_hf_compat)

    # Also stub HF_TOKEN so load_embedder doesn't raise on empty.
    import config
    monkeypatch.setattr(config, "HF_TOKEN", "dummy-token")

    from persons import embedder
    embedder.load_embedder()

    assert called["patch"], "load_embedder must call patch_hf_hub_use_auth_token"
    assert called["pretrained"], "load_embedder must instantiate PretrainedSpeakerEmbedding"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_embedder_hf_patch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.hf_compat'`.

- [ ] **Step 3: Extract the patch to `utils/hf_compat.py`**

Create `utils/hf_compat.py`:

```python
"""
Compatibility shim for huggingface_hub >=1.x after pyannote 3.3.2.

pyannote.audio 3.3.2 still passes the deprecated `use_auth_token=` kwarg
down to `huggingface_hub.hf_hub_download`. huggingface_hub 1.x dropped that
alias. We translate it transparently by rebinding every `hf_hub_download`
reference already imported across `sys.modules`, plus the source module.

Call this BEFORE any code path that loads pyannote (diarizer, embedder).
Idempotent — safe to call many times.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

_patched = False


def patch_hf_hub_use_auth_token() -> None:
    """Install the `use_auth_token` → `token` translation shim. Idempotent."""
    global _patched
    if _patched:
        return
    import huggingface_hub

    orig = huggingface_hub.hf_hub_download

    def _shim(*args, **kwargs):
        if "use_auth_token" in kwargs:
            kwargs.setdefault("token", kwargs.pop("use_auth_token"))
        return orig(*args, **kwargs)

    replaced = 0
    huggingface_hub.hf_hub_download = _shim
    replaced += 1
    try:
        import huggingface_hub.file_download as fd
        if getattr(fd, "hf_hub_download", None) is orig:
            fd.hf_hub_download = _shim
            replaced += 1
    except ImportError:
        pass
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        try:
            if getattr(mod, "hf_hub_download", None) is orig:
                mod.hf_hub_download = _shim
                replaced += 1
        except Exception:  # noqa: BLE001 — some modules raise on attr access
            continue
    _patched = True
    log.info("hf_compat: patched hf_hub_download (use_auth_token -> token) in %d module(s)", replaced)
```

- [ ] **Step 4: Wire load_embedder to call the patch first**

Modify `persons/embedder.py`. In `load_embedder`, immediately after the `if not HF_TOKEN:` check and BEFORE the pyannote import, add:

```python
    from utils.hf_compat import patch_hf_hub_use_auth_token
    patch_hf_hub_use_auth_token()
```

So the function looks like:

```python
def load_embedder():
    """Lazy-instantiate PretrainedSpeakerEmbedding. Singleton."""
    global _model, _device
    if _model is not None:
        return _model
    if not HF_TOKEN:
        raise RuntimeError(
            "HUGGINGFACE_TOKEN / HF_TOKEN must be set to load pyannote/embedding"
        )
    from utils.hf_compat import patch_hf_hub_use_auth_token
    patch_hf_hub_use_auth_token()
    import torch
    from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _model = PretrainedSpeakerEmbedding(
        EMBEDDING_MODEL,
        device=_device,
        use_auth_token=HF_TOKEN,
    )
    log.info("loaded pyannote/embedding on %s", _device)
    return _model
```

- [ ] **Step 5: Replace the inline patch in stage2_transcribe_diarize.py**

In `stage2_transcribe_diarize.py`:
1. DELETE the existing `_hf_hub_patched = False` module-level variable.
2. DELETE the entire `_patch_hf_hub_use_auth_token` function body (keep the function as a one-liner alias during transition).
3. In `load_diarizer`, replace the call `_patch_hf_hub_use_auth_token()` with:

```python
    from utils.hf_compat import patch_hf_hub_use_auth_token
    patch_hf_hub_use_auth_token()
```

Concretely, at the top of `stage2_transcribe_diarize.py` the `_hf_hub_patched = False` line gets removed. The body of `_patch_hf_hub_use_auth_token` is replaced with:

```python
def _patch_hf_hub_use_auth_token() -> None:
    """Deprecated module-local alias; forwards to utils.hf_compat."""
    from utils.hf_compat import patch_hf_hub_use_auth_token as _p
    _p()
```

- [ ] **Step 6: Also invoke the patch from `run.preflight` as belt-and-braces**

In `run.py:preflight()`, after `pin_to_p_cores()` and after the reconcile call from Task 4, append:

```python
    # Make sure the hf_hub use_auth_token shim is installed early — covers
    # the redo path which skips stage 2 (SMAC Finding #9).
    from utils.hf_compat import patch_hf_hub_use_auth_token
    patch_hf_hub_use_auth_token()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_embedder_hf_patch.py -v`
Expected: 2 PASS.

Run the regression tests:
`.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all tests from Tasks 1-7 still pass.

- [ ] **Step 8: Compile + commit**

Run: `.venv/Scripts/python.exe -m py_compile utils/hf_compat.py persons/embedder.py stage2_transcribe_diarize.py run.py`

```bash
git add utils/hf_compat.py persons/embedder.py stage2_transcribe_diarize.py run.py tests/test_embedder_hf_patch.py
git commit -m "fix(embedder): extract hf_hub patch to utils.hf_compat; call from embedder + preflight"
```

---

## Final verification

- [ ] **Step 1: Run the full test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all new tests pass (8 tests across 8 new test files + existing tests from the repo).

- [ ] **Step 2: Run the smoke test (skip disk check)**

Run: `.venv/Scripts/python.exe run.py --skip-disk-check`
Expected: both test files in `Material/test_smoke/` process clean with `complete: 2 ok / 2 attempted.` in the tail of the latest log under `_logs/`.

- [ ] **Step 3: Sanity-check the redo path**

Run: `.venv/Scripts/python.exe run.py --redo --threshold 1 --dry-run`
Expected: dry-run lists the two polished files as candidates (both were processed before Task 6's trust counter existed, so their stamp shows `bootstrap_sessions_remaining` missing which `is_stale` now treats appropriately after Task 3+7 changes).

- [ ] **Step 4: Verify the SMAC-flagged bugs no longer appear**

For each finding, spot-check:
- Task 1: `grep -c "nvidia-cudnn-cu11" requirements.txt` → 1
- Task 2: `grep -c "atomic_write_wav" stage1_isolate.py` → 1
- Task 3: `grep -c "is_redo" stage3_postprocess.py` → ≥5
- Task 4: `grep -c "reconcile_from_polished" persons/corpus.py` → 1
- Task 5: `grep -c "PITCH_EXTRACTOR" persons/regionizer.py` → ≥2
- Task 6: `grep -c "bootstrap_sessions_remaining" persons/schema.py stage3_postprocess.py` → ≥3
- Task 7: `grep -c "if not active_centroids:" stage3_postprocess.py` → ≥1
- Task 8: `grep -c "from utils.hf_compat" persons/embedder.py stage2_transcribe_diarize.py run.py` → ≥3

- [ ] **Step 5: Final commit with summary**

```bash
git log --oneline -10
```

Should show 8 new commits, one per task, in order.

---

## Out of scope for this plan

These SMAC findings are confirmed but deferred to a follow-up:

- **Non-atomic `np.save` for per-region centroids** (Finding #11): needs an `atomic_write_npy` helper and careful rollout across 3 call sites — worth its own plan.
- **Corpus read-modify-write race** (Finding #8): needs file-level locking (`fcntl`/`msvcrt`) — Windows + POSIX divergence deserves its own plan.
- **`_extract_json` multi-array misparse** (Finding #13), **registry.rename un-stales** (#14), **flag_collision orphans** (#15), **--redo --all filter semantics** (#16), **diarize sample_rate hardcoded** (#17), **hf_hub patch single-walk** (#18), **non-Windows DLL silent return** (#19), **polish_chunk_cli FileNotFoundError** (#20), **segment_by_region overhang** (#21): MED-impact or refinements to already-working behavior — append to backlog for next cycle.
- **UNVERIFIED findings** (#22, #23, #27, #28): from_dict type validation, _push_recent log, pitch_range monotonic, is_stale null-state. All MED/HIGH impact but coverage gap in SMAC — worth a follow-up audit pass with verifier.
- **LOW-impact findings** (#24–#26, #29): validate_chunk empty text, batch summary enumerate, spectral gate relative, is_transient substring — all cosmetic / defensive, low urgency.
