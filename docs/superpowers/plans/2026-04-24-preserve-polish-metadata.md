# Preserve Polish Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve original transcript segment metadata when CLI or API polish succeeds.

**Architecture:** Keep the current prompt and validation contract, but add one merge helper that copies each original segment and only applies the polished text plus the `polished=True` audit flag. Wire both CLI and API success paths through that helper so fallback behavior remains unchanged.

**Tech Stack:** Python 3, pytest, existing `persons.polish_engine` module.

---

## File Structure

- Modify: `persons/polish_engine.py`
- Test: `tests/test_polish_engine_preserves_metadata.py`

`persons/polish_engine.py` keeps responsibility for polish backend dispatch, JSON validation, and merge behavior. Add a private helper named `_merge_polished_segments(original, polished)` near `validate_chunk()` because it depends on the same validated shape.

`tests/test_polish_engine_preserves_metadata.py` is a focused regression file. It tests the helper directly, then tests CLI and API success paths so both backends stay wired to the same preservation behavior.

No docs update is required. This is a bugfix to existing behavior, not a new user-facing feature or tool.

---

### Task 1: Add Direct Regression Tests For Metadata Preservation

**Files:**
- Create: `tests/test_polish_engine_preserves_metadata.py`
- Modify: none
- Test: `tests/test_polish_engine_preserves_metadata.py`

- [ ] **Step 1: Create the failing helper-level test file**

Create `tests/test_polish_engine_preserves_metadata.py` with this complete content:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
```

- [ ] **Step 2: Run helper tests to verify they fail**

Run:

```bash
pytest tests/test_polish_engine_preserves_metadata.py -v
```

Expected: FAIL during import with this shape:

```text
ImportError: cannot import name '_merge_polished_segments' from 'persons.polish_engine'
```

- [ ] **Step 3: Commit the failing tests**

Run:

```bash
git add tests/test_polish_engine_preserves_metadata.py
git commit -m "test: cover polish metadata preservation"
```

Expected: commit succeeds. If project policy forbids committing failing tests, skip this commit and commit after Task 2 passes.

---

### Task 2: Implement The Shared Metadata Merge Helper

**Files:**
- Modify: `persons/polish_engine.py:303-318`
- Test: `tests/test_polish_engine_preserves_metadata.py`

- [ ] **Step 1: Add `_merge_polished_segments` below `validate_chunk`**

In `persons/polish_engine.py`, insert this function immediately after `validate_chunk()`:

```python
def _merge_polished_segments(original: list[dict], polished: list[dict]) -> list[dict]:
    """Copy original segments and apply only trusted polish output fields."""
    out: list[dict] = []
    for o, p in zip(original, polished):
        next_seg = dict(o)
        next_seg["text"] = str(p.get("text", o.get("text", "")))
        next_seg["polished"] = True
        out.append(next_seg)
    return out
```

The helper intentionally ignores every LLM-returned key except `text`. `validate_chunk()` already proves length, timestamps, and `speaker_id` match; all other trusted fields must come from the original segment.

- [ ] **Step 2: Run helper tests to verify they pass**

Run:

```bash
pytest tests/test_polish_engine_preserves_metadata.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 3: Run existing polish skip tests**

Run:

```bash
pytest tests/test_polish_engine_should_skip.py -v
```

Expected:

```text
6 passed
```

- [ ] **Step 4: Commit helper implementation**

Run:

```bash
git add persons/polish_engine.py tests/test_polish_engine_preserves_metadata.py
git commit -m "fix: preserve metadata when merging polished text"
```

Expected: commit succeeds.

---

### Task 3: Wire CLI And API Success Paths Through The Helper

**Files:**
- Modify: `persons/polish_engine.py:166-169`
- Modify: `persons/polish_engine.py:216-219`
- Modify: `tests/test_polish_engine_preserves_metadata.py`
- Test: `tests/test_polish_engine_preserves_metadata.py`

- [ ] **Step 1: Extend tests for CLI and API success paths**

Append this code to `tests/test_polish_engine_preserves_metadata.py`:

```python
import asyncio
import json
from types import SimpleNamespace

import persons.polish_engine as _pe


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
```

- [ ] **Step 2: Run backend-path tests to verify they fail**

Run:

```bash
pytest tests/test_polish_engine_preserves_metadata.py -v
```

Expected: helper tests pass, CLI/API tests fail with missing metadata keys such as:

```text
KeyError: 'speaker_name'
```

- [ ] **Step 3: Replace CLI success return**

In `persons/polish_engine.py`, change the successful return in `polish_chunk_cli()` from:

```python
    return [dict(p, polished=True) for p in parsed]
```

to:

```python
    return _merge_polished_segments(chunk, parsed)
```

- [ ] **Step 4: Replace API success return**

In `persons/polish_engine.py`, change the successful return in `polish_chunk_api()` from:

```python
    return [dict(p, polished=True) for p in parsed]
```

to:

```python
    return _merge_polished_segments(chunk, parsed)
```

- [ ] **Step 5: Run focused tests to verify they pass**

Run:

```bash
pytest tests/test_polish_engine_preserves_metadata.py -v
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Run existing polish tests**

Run:

```bash
pytest tests/test_polish_engine_should_skip.py tests/test_polish_diff.py -v
```

Expected: all selected tests pass. Current expected count is the sum reported by pytest for those files; failures in existing tests mean the merge helper changed unrelated polish behavior and must be corrected before proceeding.

- [ ] **Step 7: Commit backend wiring**

Run:

```bash
git add persons/polish_engine.py tests/test_polish_engine_preserves_metadata.py
git commit -m "fix: route polish backends through metadata merge"
```

Expected: commit succeeds.

---

### Task 4: Verify Full Python Regression Surface

**Files:**
- Modify: none
- Test: Python test suite

- [ ] **Step 1: Run the complete pytest suite**

Run:

```bash
pytest -q
```

Expected: full suite passes.

- [ ] **Step 2: Inspect the final diff**

Run:

```bash
git diff --stat
git diff -- persons/polish_engine.py tests/test_polish_engine_preserves_metadata.py
```

Expected: diff only adds `_merge_polished_segments`, replaces the two success returns, and adds the focused tests. No unrelated cleanup or formatting churn.

- [ ] **Step 3: Final commit if previous commits were skipped**

Run only if Tasks 1-3 were not committed separately:

```bash
git add persons/polish_engine.py tests/test_polish_engine_preserves_metadata.py
git commit -m "fix: preserve polish segment metadata"
```

Expected: commit succeeds, or Git says there is nothing to commit because earlier task commits already captured the changes.

---

## Self-Review

Spec coverage: The plan preserves metadata after successful polish, covers both CLI and API return paths, keeps validation behavior, and tests non-mutation of inputs.

Placeholder scan: No implementation step relies on unspecified validation, error handling, or unnamed tests.

Type consistency: `_merge_polished_segments(original: list[dict], polished: list[dict]) -> list[dict]` is defined before both backend wiring steps use it, and all tests import the same helper name.
