# Evidence-Gated Diarization Trust Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a measurement-first diarization trust layer that replaces false speaker certainty with benchmarked, explicit uncertainty while keeping Transcriptor stable on the user's Windows 11 GTX 1080 Ti machine.

**Architecture:** Keep `Electron UI -> electron/bridge.py -> backend/process_v2.py`. Add a benchmark harness in `backend/tests`, move diarization work to a shared sidecar-backed contract used by both live and resume paths, emit explicit `ok | partial | failed` outcomes, and only then promote quality-first Whisper defaults after the benchmark proves they help.

**Tech Stack:** Electron, plain browser JavaScript, Python, pytest, node:test, faster-whisper, pyannote.audio, FFmpeg

---

**Supersedes:** `docs/superpowers/plans/2026-04-16-diarization-accuracy-fixes.md`

## File Structure

**Create**
- `backend/core/benchmark_metrics.py`
- `backend/core/diarization_contract.py`
- `backend/tests/test_benchmark_metrics.py`
- `backend/tests/test_benchmark_pack.py`
- `backend/tests/test_diarization_contract.py`
- `backend/tests/fixtures/benchmark_pack/manifest.json`
- `backend/tests/fixtures/benchmark_pack/holdout_manifest.json`

**Modify**
- `backend/core/config_loader.py`
- `backend/core/diarizer.py`
- `backend/process_v2.py`
- `backend/tests/test_config.py`
- `backend/tests/test_diarizer.py`
- `backend/tests/test_process_v2.py`
- `backend/tests/test_bridge.py`
- `backend/tests/test_golden.py`
- `backend/tests/fixtures/README.md`
- `electron/bridge.py`
- `electron/main.js`
- `electron/resources/settings_state.js`
- `electron/resources/index.html`
- `electron/resources/app.js`
 - `electron/resources/styles.css`
 - `electron/tests/settings_state.test.js`

### Task 1: Benchmark Gate

Files:
- Create backend/core/benchmark_metrics.py
- Create backend/tests/test_benchmark_metrics.py
- Create backend/tests/test_benchmark_pack.py
- Create backend/tests/fixtures/benchmark_pack/manifest.json
- Create backend/tests/fixtures/benchmark_pack/holdout_manifest.json
- Modify backend/tests/fixtures/README.md

- [ ] Step 1: Add failing metric tests for word error rate, speaker label accuracy, and degraded rate.
- [ ] Step 2: Run the metric tests and verify they fail on the missing helper module.
- [ ] Step 3: Implement the three metric helpers.
- [ ] Step 4: Add failing benchmark-pack tests for required buckets, disjoint holdout IDs, and threshold fields.
- [ ] Step 5: Run the benchmark-pack tests and verify they fail on missing manifests.
- [ ] Step 6: Add the main manifest, the blind holdout manifest, and README rules for hand-labeled references.
- [ ] Step 7: Re-run the metric and benchmark tests and verify pass, with integration cases only skipping when audio is not committed.
- [ ] Step 8: Commit.

### Task 2: Shared Diarization Contract

Files:
- Create backend/core/diarization_contract.py
- Create backend/tests/test_diarization_contract.py
- Modify backend/process_v2.py
- Modify backend/tests/test_process_v2.py

- [ ] Step 1: Add failing tests for ok, partial, and failed outcome classification.
- [ ] Step 2: Add failing tests proving the queue stores sidecar paths instead of full Whisper result dicts.
- [ ] Step 3: Run the diarization contract and process tests and verify fail.
- [ ] Step 4: Implement build_diarization_outcome with status, text, assigned_labels, uncertain_labels, and reason.
- [ ] Step 5: Change save-and-queue logic to enqueue sidecar path plus output path only.
- [ ] Step 6: Add one shared helper in process_v2 so both live workers and run_diarize_pass use the same diarization application path.
- [ ] Step 7: Extend diarization_done heartbeat payloads to include status and reason.
- [ ] Step 8: Re-run the tests and verify pass.
- [ ] Step 9: Commit.

### Task 3: Uncertainty Labels and Path Input

Files:
- Modify backend/core/diarizer.py
- Modify backend/tests/test_diarizer.py

- [ ] Step 1: Add failing tests for Unknown, Overlapped, and Partial speaker states plus visible transcript labels.
- [ ] Step 2: Add a failing test that prefers path-based pyannote input and only falls back to waveform dict input when needed.
- [ ] Step 3: Run the diarizer tests and verify fail.
- [ ] Step 4: Make diarize try the WAV path directly first.
- [ ] Step 5: Return both speaker and speaker_state from the overlap picker.
- [ ] Step 6: Preserve Unknown, Overlapped, and Partial labels in formatted transcript output.
- [ ] Step 7: Re-run the diarizer tests and verify pass.
- [ ] Step 8: Commit.

### Task 4: Honest Bridge and Renderer Status

Files:
- Modify electron/bridge.py
- Modify backend/tests/test_bridge.py
- Modify electron/resources/app.js
- Modify electron/resources/styles.css

- [ ] Step 1: Add a failing bridge test for file_done payloads that carry diarization_status.
- [ ] Step 2: Run the bridge tests and verify fail.
- [ ] Step 3: Extract a testable helper that builds file_done payloads.
- [ ] Step 4: Thread diarization status through the heartbeat drain path in bridge.py.
- [ ] Step 5: Update app.js so completed files render speaker labels ready, partial, or unavailable honestly.
- [ ] Step 6: Add a CSS state for partial diarization.
- [ ] Step 7: Re-run the bridge tests and verify pass.
- [ ] Step 8: Commit.

### Task 5: Quality-First Defaults After the Benchmark Exists

Files:
- Modify electron/resources/settings_state.js
- Modify electron/tests/settings_state.test.js
- Modify electron/resources/index.html
- Modify electron/main.js
- Modify electron/bridge.py
- Modify backend/core/config_loader.py
- Modify backend/tests/test_config.py
- Modify backend/tests/test_bridge.py
- Modify backend/tests/test_golden.py

- [ ] Step 1: Add failing tests for Electron defaults and backend config defaults.
- [ ] Step 2: Run the settings, config, and bridge tests and verify fail.
- [ ] Step 3: Promote the default model to large-v3, the default beam size to 3, and keep speaker count on auto-detect.
- [ ] Step 4: Align the golden regression test with that benchmarked profile.
- [ ] Step 5: Re-run the settings, config, bridge, and golden tests and verify pass, with integration tests only skipping when fixtures are missing.
- [ ] Step 6: Commit.

### Final Verification

Files:
- Modify only the planned benchmark, diarization, bridge, renderer, and config files above.

- [ ] Step 1: Run the focused Python suite and verify pass.
- [ ] Step 2: Run the Electron settings test and verify pass.
- [ ] Step 3: Run the integration gate and verify pass or guarded skip.
- [ ] Step 4: Review the final git diff and verify only the benchmark gate, trust layer, bounded queue, honest status, and default-profile changes are present.
- [ ] Step 5: Final commit.

## Execution Handoff

Plan complete. Recommended execution mode: subagent-driven, one task at a time with review between tasks.
