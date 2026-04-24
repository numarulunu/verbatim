# Transcriptor v2 — Backlog

Issues discovered via audit / usage, tracked for prioritization.

## From SMAC 2026-04-21 (concurrency/resumability audit)

Full report: `~/Desktop/Claude/skills-archive/smac/runs/2026-04-21-concurrency-resumability-bugs.md`

### [NEW] Non-atomic acapella write breaks resume guarantee
- Impact: HIGH | Effort: LOW | Confidence: 95%
- Evidence: stage1_isolate.py:117
- Problem: `sf.write()` isn't wrapped in atomic tmp-then-rename. Crash mid-write leaves corrupt acapella; `needs_processing` only checks polished JSON so corrupt acapella is reused forever.
- Fix: wrap in atomic_write_bytes via BytesIO + os.replace.

### [NEW] Redo double-counts sessions and re-blends same audio into voice libs
- Impact: HIGH | Effort: MED | Confidence: 90%
- Evidence: stage3_postprocess.py:325 + 334 + 350-353
- Problem: On --redo, n_prior=1 from first pass, running-mean averages same audio twice; session counters also double-increment.
- Fix: thread is_redo through to _update_one_person; skip blend + counter increments on redo.

### [NEW] Missing NVIDIA runtime pins in requirements.txt
- Impact: HIGH | Effort: LOW | Confidence: 90%
- Evidence: requirements.txt (absent entries for nvidia-cublas-cu12, nvidia-cuda-runtime-cu12, nvidia-cudnn-cu11, speechbrain<1.0)
- Problem: Gate 5 installed these ad-hoc; fresh install will break.
- Fix: pin in a Windows GPU runtime section of requirements.txt.

### [NEW] finalize writes polished JSON before corpus — orphan on corpus failure
- Impact: HIGH | Effort: MED | Confidence: 90%
- Evidence: stage3_postprocess.py:394-396
- Problem: polished JSON commits first; corpus write failure leaves file appearing "done" to needs_processing but missing from corpus.json. No reconciler.
- Fix: add corpus-vs-polished reconciler on startup OR write corpus first.

### [NEW] pyworld vs librosa frame-period mismatch in _has_sustained_pitch
- Impact: HIGH | Effort: LOW | Confidence: 90%
- Evidence: regionizer.py:149 (hardcoded 512.0/sr = 32ms) vs :64 (pyworld frame_period=10ms)
- Problem: SUSTAIN_MIN_SECONDS uses librosa hop unconditionally; pyworld produces ~3.2x more frames; sung_full false-fires after 46 frames instead of 150.
- Fix: derive frame_s from PITCH_EXTRACTOR (0.010 for pyworld, 512/sr for librosa).

### [NEW] Bootstrap confidence=1.0 bypasses the 0.75 poisoning guard on sessions 2-3
- Impact: HIGH | Effort: LOW | Confidence: 85%
- Evidence: stage3_postprocess.py:92, 109
- Problem: Gate-5 fix set bootstrap confidence to 1.0; no "first 3 sessions" trust counter exists, so NEW_PERSON_CONFIDENCE_GATE=0.75 on sessions 2-3 is dead code.
- Fix: per-person trust counter; real match-based confidence required on sessions 2-3.

### [NEW] _update_one_person silent-skips universal.npy while still incrementing n_sessions
- Impact: HIGH | Effort: LOW | Confidence: 85%
- Evidence: stage3_postprocess.py:342 (guard) vs 350-353 (counter outside guard)
- Problem: No region >=10s leaves active_centroids empty, universal/recent skipped, but session counts still increment. After 3 skips, person passes first-3-sessions gate with no fingerprint data.
- Fix: either abort session-count update on empty active_centroids, or force-write a degraded universal.

### [NEW] Corpus replace_session has read-modify-write race
- Impact: MED | Effort: MED | Confidence: 88%
- Evidence: persons/corpus.py:62
- Problem: load then filter then atomic_write. Two overlapping processes overwrite each other. No file-level lock.
- Fix: fcntl.flock (POSIX) / msvcrt.locking (Windows) on corpus.json.lock sibling.

### [NEW] load_embedder uses use_auth_token without calling the hf_hub patch
- Impact: MED | Effort: LOW | Confidence: 85%
- Evidence: persons/embedder.py:43-46 (no _patch_hf_hub_use_auth_token call)
- Problem: In --redo mode _redo_one skips stage 2 so hf_hub patch (only in load_diarizer) never runs; embedder crashes with unexpected kwarg on fresh venv.
- Fix: move the patch to run.preflight OR have load_embedder call it defensively.

### [NEW] Silence classified as speaking, accumulated to voice library
- Impact: MED | Effort: LOW | Confidence: 80%
- Evidence: regionizer.py:137
- Problem: No-voice segments default to "speaking" and get embedded into the person's speaking centroid. Universal drifts toward silence/noise.
- Fix: add a "silence" sentinel; filter from accumulation in stage3.

### [NEW] Non-atomic np.save for per-region centroids
- Impact: MED | Effort: MED | Confidence: 80%
- Evidence: stage3_postprocess.py:333, 345, 374
- Problem: Crash between np.save calls leaves a person's library half-updated — some regions fresh, others stale. No transaction semantics.
- Fix: add atomic_write_npy with .tmp + os.replace.

### [NEW] needs_processing ignores partial state between stage 1 and stage 3
- Impact: MED | Effort: LOW | Confidence: 78%
- Evidence: run.py:116
- Problem: Only checks polished JSON. Stage-2 sidecars never consulted; utils/checkpoint.py has zero call sites.
- Fix: write 02_raw_json/<fid>.stage2.json after stage 2; consult via utils.checkpoint.is_fresh.

### [NEW] _extract_json misparses responses with multiple JSON arrays
- Impact: MED | Effort: LOW | Confidence: 70%
- Evidence: persons/polish_engine.py:296
- Problem: text.find-open plus text.rfind-close captures from first open to last close, including prose between multiple arrays.
- Fix: regex for the last balanced JSON array; or prompt "respond with exactly one JSON array."

### [NEW] registry.rename silently un-stales files
- Impact: MED | Effort: LOW | Confidence: 70%
- Evidence: persons/redo.py:52
- Problem: After rename(old,new), is_stale skips old (continue on missing from current_state) — file NOT flagged for redo, contradicting registry.rename's own log.
- Fix: track aliases OR treat missing-from-current-state as stale.

### [NEW] flag_collision crash-safety: orphan universal.npy on bootstrap failure
- Impact: MED | Effort: LOW | Confidence: 70%
- Evidence: persons/matcher.py bootstrap_new_person order (register_new then np.save)
- Problem: If bootstrap fails between np.save(universal.npy) and registry.save completing, orphan voiceprints persist without metadata.json.
- Fix: save npy files AFTER metadata.json; or reconcile on startup.

### [NEW] --redo --all still applies participant / confidence filters
- Impact: MED | Effort: LOW | Confidence: 70%
- Evidence: persons/redo.py:95
- Problem: Only threshold is bypassed. `--redo --all --student madalina` with no madalina files returns empty silently.
- Fix: make --all truly nuclear (skip all filters) OR document the AND in --help.

### [NEW] diarize hardcodes sample_rate=16000 without validation
- Impact: MED | Effort: LOW | Confidence: 70%
- Evidence: stage2_transcribe_diarize.py:369
- Problem: Asserts 16kHz without input check; practically safe today but fragile to refactors.
- Fix: pass sr through diarize(audio, sr=16000) with entry assertion.

### [NEW] hf_hub patch walks sys.modules once — late imports bypass
- Impact: MED | Effort: LOW | Confidence: 70%
- Evidence: stage2_transcribe_diarize.py:313
- Problem: Modules imported AFTER the patch get the unpatched hf_hub_download. Currently safe; regresses with new modules.
- Fix: patch huggingface_hub.file_download.hf_hub_download at definition site.

### [NEW] _register_cuda_dll_paths silent early-return on non-Windows
- Impact: LOW | Effort: LOW | Confidence: 70%
- Evidence: stage2_transcribe_diarize.py:74-75
- Problem: No log line on non-Windows; easy to miss why DLLs weren't preloaded.
- Fix: log.info at entry noting platform + DLL preload skip.

### [NEW] polish_chunk_cli catches FileNotFoundError as transient
- Impact: MED | Effort: LOW | Confidence: 70%
- Evidence: persons/polish_engine.py:122
- Problem: Missing claude CLI is fatal config error, not transient. Every file silently falls back to raw.
- Fix: split except; FileNotFoundError raises (or logs CRITICAL); TimeoutExpired retains raw.

### [NEW] segment_by_region window overhangs short utterances
- Impact: MED | Effort: MED | Confidence: 70%
- Evidence: regionizer.py:179
- Problem: Utterances <1.5s get a window extending past actual audio; padding mislabels Q&A turns as sung_full / sung_high.
- Fix: clamp window to min(win, len(audio)); skip classification for <0.5s, label "speaking".

### [NEW] schema.from_dict does not validate region_session_counts value types
- Impact: HIGH | Effort: LOW | Confidence: 80% (UNVERIFIED)
- Evidence: persons/schema.py:47-54
- Problem: Corrupt or hand-edited metadata.json with string values breaks _update_one_person mid-session with TypeError.
- Fix: coerce numeric fields in from_dict.

### [NEW] _push_recent silently replaces corrupted 1-D ring without logging
- Impact: HIGH | Effort: LOW | Confidence: 80% (UNVERIFIED)
- Evidence: stage3_postprocess.py:367-368
- Problem: Recovery path for corrupted recent.npy loses all prior ring history silently.
- Fix: log.warning on reset path.

### [NEW] is_transient substring match false-positives on fatal CUDA errors
- Impact: MED | Effort: LOW | Confidence: 70%
- Evidence: utils/retry.py:22
- Problem: "cuda" substring matches fatal config/kernel errors; retries 3x unnecessarily. Currently harmless (with_retry unused) but wired in spec.
- Fix: tighten to exact-message matching before activating with_retry.

### [NEW] update_pitch_range never shrinks — early bad data persists forever
- Impact: MED | Effort: LOW | Confidence: 70% (UNVERIFIED)
- Evidence: persons/regionizer.py:212
- Problem: Early bad pitch extraction permanently inflates the person's range band.
- Fix: rolling-window percentiles across last N sessions; manual reset via enroll.py edit.

### [NEW] is_stale returns False when processed_at_db_state is null
- Impact: MED | Effort: LOW | Confidence: 70% (UNVERIFIED)
- Evidence: persons/redo.py:42
- Problem: Files with missing / corrupt stamps never get re-processed on --redo.
- Fix: treat missing stamp as definitely-stale.

### [NEW] Empty text field accepted by validate_chunk
- Impact: LOW | Effort: LOW | Confidence: 70%
- Evidence: persons/polish_engine.py:270
- Problem: LLM response with empty text passes validation; overwrites real transcript.
- Fix: add non-empty text check in validate_chunk.

### [NEW] Batch summary logs count, not enumeration of failed file_ids
- Impact: LOW | Effort: LOW | Confidence: 70%
- Evidence: run.py:306
- Problem: "290 ok / 300 attempted" doesn't tell you which 10 failed.
- Fix: collect failed file_ids; log list + optionally write _logs/last_run_failures.json.

### [NEW] Spectral gate uses per-frame relative magnitude — noise survives silent frames
- Impact: LOW | Effort: MED | Confidence: 60%
- Evidence: utils/audio_qc.py:58
- Problem: Silent frames with small transients have low peak; relative threshold keeps bins.
- Fix: hybrid (absolute floor for low-energy frames, relative for normal).

### [NEW] Busy indicator masks daemon failures
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 96% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/App.tsx:121
- **Problem:** `App` forces the top bar to display `busy` whenever a batch is active, even if the daemon status has already moved to `down`, `shutting_down`, or `crashed`. That hides real failures behind a healthy-looking header.
- **Proposed fix:** Let failure states win over `busy` in the top bar. Keep `busy` only for the healthy in-flight case and surface crash context immediately.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Renderer load failure does not stop startup
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 94% | **Verified:** CONFIRMED
- **Evidence:** verbatim/main.js:92
- **Problem:** `createWindow()` catches renderer load failure and only logs it. Startup still proceeds into `startEngine()` and `initAutoUpdater()`, so the app can boot background services without a usable renderer.
- **Proposed fix:** Treat renderer-load failure as fatal startup, or show a dedicated error window and skip engine/updater startup until the renderer is available.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Batch path cache is overwritten before the batch is confirmed
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 93% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/bridge/verbatimClient.ts:21
- **Problem:** The renderer caches batch file paths before `api.send()` resolves. A second `process_batch` request can be rejected while still replacing that global mapping, which can mis-attribute later per-file events to the wrong paths.
- **Proposed fix:** Store batch file mappings by batch id, or commit the mapping only after the matching `batch_started` event is received.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] `publish-win` skips the packaging prep steps
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 89% | **Verified:** CONFIRMED
- **Evidence:** verbatim/package.json:20
- **Problem:** `publish-win` invokes `electron-builder` directly instead of chaining through the scripts that rebuild the renderer and packaged engine. That makes stale or incomplete release artifacts possible.
- **Proposed fix:** Make `publish-win` depend on the full prep pipeline first, or route it through `build-all-win` before publishing.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] `npm start` always rebuilds the renderer
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** LOW | **Confidence:** 97% | **Verified:** CONFIRMED
- **Evidence:** verbatim/package.json:10
- **Problem:** Every Electron launch does a full renderer build first. That slows the dev loop and blocks live-renderer sessions on build failures that do not need a local bundle.
- **Proposed fix:** Split the dev launcher from the packaged-preview launcher, or skip `renderer:build` when `VERBATIM_RENDERER_URL` is set.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Corpus summary is a one-time snapshot
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** LOW | **Confidence:** 90% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/components/redo/RedoView.tsx:26
- **Problem:** Redo fetches corpus summary state only on mount and then waits for `corpus_summary` events. Nothing in the current flow refreshes that summary after redo completion or registry mutations, so the summary can stay stale.
- **Proposed fix:** Refetch corpus summary after redo completion and successful registry mutations, or add an explicit refresh action.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Every progress tick rerenders the whole file table
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** MED | **Confidence:** 88% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/components/batch/FileList.tsx:76
- **Problem:** Batch progress lives in parent state, and `FileList` maps every file row on each render. Because `FileRow` is not memoized, a single file progress update redraws the whole table.
- **Proposed fix:** Memoize `FileRow` or isolate per-row progress so unchanged rows can bail out during large batches.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Batch tab unmount drops live progress state
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 94% | **Verified:** PARTIAL
- **Evidence:** verbatim/renderer/src/App.tsx:126
- **Problem:** The Batch view is conditionally mounted. Switching tabs tears down the component that owns file progress, elapsed time, current file, and the batch event subscription. The UI-state loss is proven; the daemon-continuation part is likely but not directly demonstrated by these files.
- **Proposed fix:** Hoist batch lifecycle state and subscriptions into `App` or a shared store, then keep batch progress state alive across tab switches.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Packaged builds still honor the renderer URL override
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** LOW | **Confidence:** 83% | **Verified:** CONFIRMED
- **Evidence:** verbatim/runtime-helpers.js:55
- **Problem:** `resolveRendererTarget()` accepts `VERBATIM_RENDERER_URL` even in packaged builds. An installed app can therefore point at an external renderer instead of the bundled one based on ambient environment state.
- **Proposed fix:** Ignore the URL override in packaged mode, or require an explicit debug-only switch before honoring it.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Decode and VAD phase indices are inverted
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** LOW | **Confidence:** 99% | **Verified:** PARTIAL
- **Evidence:** verbatim/renderer/src/bridge/normalize.ts:184
- **Problem:** `normalize.ts` maps `decode` before `vad`, while `ipc-protocol.json` lists `vad` before `decode`. The verifier confirmed the protocol mismatch but downgraded the finding because `renderer/src/types.ts` already follows the renderer ordering, so the drift is protocol-to-normalizer rather than protocol-to-types.
- **Proposed fix:** Align `PHASE_ORDER` with the daemon protocol, then add a regression test that asserts numeric `phase_index` and phase names stay consistent.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Restart during startup can hang forever
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** MED | **Confidence:** 95% | **Verified:** PARTIAL
- **Evidence:** verbatim/engine-manager.js:141
- **Problem:** An orderly exit before `ready` leaves `_readyPromise` unresolved because rejection only happens on the `CRASHED` branch. The unresolved promise leak is real, but the verifier did not find direct proof that the current restart path blocks forever on it.
- **Proposed fix:** Resolve or reject the pending ready promise when the child exits before readiness, even during shutdown, so pre-ready exits do not leak unsettled startup state.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Crash details are lost across the status IPC
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** LOW | **Confidence:** 86% | **Verified:** PARTIAL
- **Evidence:** verbatim/main.js:142
- **Problem:** The status IPC exposes only the daemon state and last ready payload. Exit code and signal never reach the renderer. The verifier downgraded this because the UI can still distinguish `crashed` from `down`; what is lost is crash detail, not crash-vs-clean-shutdown state.
- **Proposed fix:** Extend the status payload with exit code, signal, or a normalized crash reason so the renderer can explain why the daemon stopped.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Packaged-launch behavior is only structurally asserted
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** MED | **Confidence:** 84% | **Verified:** PARTIAL
- **Evidence:** verbatim/tests/packaged-engine.test.js:4
- **Problem:** The current packaged test only validates paths and structural assumptions. The verifier agreed that there is no true packaged-mode smoke test, while noting that some helper-path coverage does exist already.
- **Proposed fix:** Add one packaged Electron smoke test or fixture-based packaged artifact test that exercises the resolved engine and renderer paths end to end.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Terminal batch failure details are dropped
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** LOW | **Confidence:** 84% | **Verified:** PARTIAL
- **Evidence:** verbatim/ipc-protocol.json:638
- **Problem:** The daemon protocol exposes `failures` and `total_elapsed_s` on `batch_complete`, but the renderer normalizer returns only counts. The verifier downgraded this because renderer types also omit those fields today, so the loss happens at an intentional contract boundary that still needs widening.
- **Proposed fix:** Extend the normalized batch-complete contract to include `failures` and `total_elapsed_s`, then surface them in diagnostics or batch UI.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Timeout fallback is not a true hard kill
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** LOW | **Confidence:** 84% | **Verified:** PARTIAL
- **Evidence:** verbatim/engine-manager.js:206
- **Problem:** On shutdown timeout, the manager calls `child.kill()` once and then waits indefinitely for `_exitPromise`. The verifier confirmed that this is not a robust second-stage terminate path, but noted the risk is platform-dependent because default kill semantics are stronger on Windows than POSIX.
- **Proposed fix:** Escalate from graceful shutdown to an explicit hard terminate with a second bounded wait, and add a test for a child that ignores the first stop signal.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Updater status can be missed on first paint
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** MED | **Effort:** LOW | **Confidence:** 79% | **Verified:** PARTIAL
- **Evidence:** verbatim/renderer/src/App.tsx:54
- **Problem:** Updater events are subscribe-only in the renderer and push-only in the main process. There is no replay or initial state fetch. The verifier downgraded the finding because the exact race window depends on startup timing, but the missing replay mechanism is real.
- **Proposed fix:** Cache the latest updater state in main and expose an initial getter or replay on listener registration.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Registry mutations do redundant full-list refreshes
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** LOW | **Effort:** LOW | **Confidence:** 84% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/components/registry/RegistryView.tsx:170
- **Problem:** Edit, rename, and merge each refetch the full persons list after success even though the daemon already emits targeted update events for those flows.
- **Proposed fix:** Use the targeted mutation events to update local state and reserve full list refreshes for explicit recovery paths.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

### [NEW] Role 'unknown' is advertised but cannot be saved
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-22
- **Impact:** LOW | **Effort:** LOW | **Confidence:** 96% | **Verified:** PARTIAL
- **Evidence:** verbatim/renderer/src/components/registry/RegistryView.tsx:157
- **Problem:** The edit modal offers `unknown`, but the save path only serializes teacher/student. The verifier downgraded the finding because the backend edit flow would accept an `unknown` value if sent; the proven bug is the renderer no-op plus success toast.
- **Proposed fix:** Either remove `unknown` from the editable role picker, or send and support it deliberately instead of silently dropping the selection.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-22-do-a-thorough-debugging-and.md`

## From SMAC 2026-04-23 (Electron app optimization)

Full report: `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] Daemon stderr is discarded — Python tracebacks vanish
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 98% | **Verified:** CONFIRMED
- **Evidence:** verbatim/engine-manager.js:135
- **Problem:** `child.stderr.on('data', () => {})` silently discards Python tracebacks (CUDA OOM, pyannote auth, missing HF_TOKEN). Pre-ready crashes surface only as a generic timeout; mid-batch deaths show only `{code, signal}`. Biggest diagnostic black hole in the app.
- **Proposed fix:** Buffer last ~4 KB of stderr in a ring on EngineManager; expose via `lastExit.stderr_tail` and surface in the renderer's crash banner; forward full stderr to the main-process log sink.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] No React error boundary — a render throw blanks the app
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 95% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/main.tsx:8
- **Problem:** No `ErrorBoundary` anywhere in `renderer/src/`. A render-time throw from QueuePane, SettingsRail, or any normalizer unmounts the whole tree. Toasts die with App. User sees a black window with no recovery path.
- **Proposed fix:** Wrap `<App/>` in an ErrorBoundary with a fallback UI, Copy-details button, and IPC hook to main-process log sink.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] Main-process console logs have no file sink on packaged builds
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 92% | **Verified:** CONFIRMED
- **Evidence:** verbatim/main.js:105
- **Problem:** All main-process diagnostics use bare `console.*` (L105, 198, 203, 208, 225, 247, 265). Packaged Windows builds launched from Start menu have no attached terminal — writes vanish. No `electron-log`, no `fs.appendFile`, no `app.getPath('logs')` usage.
- **Proposed fix:** Add `electron-log` (or 20-LOC fs.appendFile wrapper) early in main.js, redirect `console.{log,warn,error}`, expose IPC `open-logs-folder` action in SettingsModal.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] API tokens persisted as plaintext JSON in userData
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 90% | **Verified:** CONFIRMED
- **Evidence:** verbatim/main.js:56
- **Problem:** HF and Anthropic API keys written plaintext to `%APPDATA%\Verbatim\verbatim-settings.json`. Any process running as the user can exfiltrate both. Atomic-write is correct but irrelevant to confidentiality.
- **Proposed fix:** Store secrets via Electron `safeStorage` (DPAPI on Windows) keyed per-user; keep settings file for non-secret prefs. One-shot migration overwrites plaintext entries.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] verbatim:open-path IPC has no path / extension allowlist
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 88% | **Verified:** CONFIRMED
- **Evidence:** verbatim/main.js:176
- **Problem:** `shell.openPath(targetPath)` only rejects empty strings. A compromised renderer (XSS via remote Google Fonts CSS, bad paste, future preview feature) can run `cmd.exe`, `.bat`, `.lnk`, `.ps1`, `.msi`, `.scr` via OS-default handler.
- **Proposed fix:** Resolve to absolute real path, assert prefix matches VERBATIM_ROOT / downloads, reject dangerous extensions. For "reveal in Explorer" flows use `shell.showItemInFolder` instead.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] Unsigned installer + auto-install on quit = silent-RCE vector
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 88% | **Verified:** CONFIRMED
- **Evidence:** verbatim/main.js:207 + verbatim/build-config/electron-builder.yml:22
- **Problem:** Build is unsigned (no certificateFile/certificateSubjectName/publisherName) AND `autoInstallOnAppQuit=true` with `autoDownload=true` on public repo `numarulunu/verbatim`. electron-updater's Authenticode verification is a no-op on unsigned apps. Repo takeover = silent SYSTEM-level RCE (NSIS perMachine, Program Files). No `allowDowngrade`, `minimumSystemVersion`, or `electronUpdaterCompatibility`.
- **Proposed fix:** (1) Flip `autoInstallOnAppQuit=false` + explicit IPC prompt until signed; (2) add code-signing via `win.certificateSubjectName`; (3) add `electronUpdaterCompatibility: '>=0.1.7'` for rollback protection.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] resource_stats tick rerenders entire App tree every second
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 88% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/App.tsx:80
- **Problem:** `stats` lives in root App state, replaced on every `resource_stats` event. Each tick re-runs `useBatchWorkspace`, re-derives scanSummary/completedCount, and re-renders QueuePane/SettingsRail/BottomActionBar. Stats is consumed only by BottomActionBar. Second independent source amplifying the already-tracked FileList storm.
- **Proposed fix:** Lift stats into a `ResourceStatsContext` or move the `onEvent('resource_stats')` subscription into BottomActionBar itself — only the footer rerenders.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] Exit handler overwrites _lastExit after error, losing crash message
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 85% | **Verified:** CONFIRMED
- **Evidence:** verbatim/engine-manager.js:147
- **Problem:** Error handler at L141 stores `{code:null, signal:'ERROR', message:err.message}`. Node emits exit after error; L147 unconditionally overwrites with `{code, signal}`, losing the message. Distinct from the tracked "crash details lost across status IPC" — this is prior to IPC, at the manager level.
- **Proposed fix:** Merge rather than replace — `this._lastExit = { ...(this._lastExit || {}), code, signal };`
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] artifactName mismatches docs/packaging.md installer filename
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 92% | **Verified:** CONFIRMED
- **Evidence:** verbatim/build-config/electron-builder.yml:23
- **Problem:** Installer ships as `Verbatim-Transcribe-Setup-X.Y.Z.exe`; docs/packaging.md lines 3, 51, 116 all reference the older `Verbatim Setup X.Y.Z.exe`. Release notes and ship-gate checklist point at the wrong name.
- **Proposed fix:** Pick one source of truth (drop custom artifactName OR rewrite docs). Add a test comparing the yml key to the docs string.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] No CSP, no setWindowOpenHandler, no will-navigate guard
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 92% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/index.html:8
- **Problem:** Renderer loads remote Google Fonts CSS with no CSP meta. `main.js` installs no `setWindowOpenHandler` or `will-navigate` handler. A compromised CDN response or injected markup can open off-origin windows or navigate away from `file://`. contextIsolation/sandbox/nodeIntegration=false mitigate but do not replace a CSP.
- **Proposed fix:** Add CSP meta allowing `fonts.googleapis.com`/`fonts.gstatic.com` only. In createWindow: `setWindowOpenHandler(() => ({action:'deny'}))` + `will-navigate` preventDefault on off-origin. Bonus: self-host fonts, drop CDN.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] StrictMode double-mounts every onEvent subscription in dev
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 90% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/main.tsx:7
- **Problem:** Every effect in useBatchWorkspace/RegistryView/RedoView/App.tsx mounts→unmounts→remounts on first render in dev. `batchPathState` is a module-level singleton — second subscription's `batchPathState.clear()` on `batch_complete` can race with in-flight delivery to first subscription's stale closure. Production strips StrictMode, so it's a dev-only trap.
- **Proposed fix:** Either remove StrictMode (Electron renderer rarely benefits) or reference-count preload channels per subscriber and key `batchPathState` against double-wiring.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] No render-process-gone / gpu-process-crashed handler
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 90% | **Verified:** CONFIRMED
- **Evidence:** verbatim/main.js:108
- **Problem:** Only `mainWindow.on('closed')` wired. Zero `render-process-gone`/`gpu-process-crashed` handlers. Renderer OOM/native fault/Chromium bug leaves a white window with no auto-recovery, no log, no user message.
- **Proposed fix:** In createWindow add `webContents.on('render-process-gone', (_e, details) => { log(details); mainWindow.reload(); })`. ~10 LOC.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] App.tsx bootstrap + verbatim:open-path are fully untested
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** MED | **Confidence:** 85% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/App.tsx:57
- **Problem:** App.tsx L57 and L64 swallow `status()`/`updateStatus()` rejections silently. 16 test files cover engine-manager/preload/status — none exercise App bootstrap, `open-path` IPC, or corrupted-settings fallback. `shell-layout.test.js:158` only regex-parses JSX source.
- **Proposed fix:** Three tests — (1) toast when initial status() rejects; (2) open-path returns `{ok:false,error}` when shell.openPath yields a string; (3) loadSettings logs a warning + renames corrupt file to `verbatim-settings.broken.json` instead of silently returning `{}`.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] Vite config defaults-only — no chunking, target, drop console
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 82% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/vite.config.ts:4
- **Problem:** 7-line defaults-only config. No `build.target` pinned to Chromium, no `manualChunks` splitting react/lucide-react, no `esbuild.drop: ['console','debugger']`, no explicit `sourcemap:false`. Icons all land in the main chunk; cold-start loads a monolithic bundle.
- **Proposed fix:** Add `build.target:'chrome120'`, `sourcemap:false`, `manualChunks:{react:['react','react-dom'], icons:['lucide-react']}`, `esbuild.drop:['console','debugger']`.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] elapsed 500ms interval cascades through hook return object
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** MED | **Confidence:** 80% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/hooks/useBatchWorkspace.ts:95
- **Problem:** 500ms interval while running. Hook returns fresh object literal → App rerenders → new-identity props to SettingsRail/QueuePane/BottomActionBar. Full subtree reconciliation twice per second for the entire batch. `elapsed` is consumed only by BottomActionBar.
- **Proposed fix:** Same pattern as resource_stats — isolate elapsed into BottomActionBar (pass batchStartedAt + running, compute locally).
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] build-win script skips fetch-ffmpeg + build-engine prep
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 85% | **Verified:** PARTIAL
- **Evidence:** verbatim/package.json:18
- **Problem:** `build-win` only chains `renderer:build` + electron-builder. Running it directly packages whatever stale `engine/` is on disk. Only `build-all-win` and `publish-win` run the prep chain. Tests guard `publish-win` only. The inverse half of the already-tracked publish-win footgun.
- **Proposed fix:** Either make `build-win` depend on fetch-ffmpeg+build-engine, or rename current script to `build-win:electron-only` and alias `build-win`→`build-all-win`. Extend test coverage.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] readline and stderr listener never torn down on exit
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 80% | **Verified:** PARTIAL
- **Evidence:** verbatim/engine-manager.js:130
- **Problem:** Neither `rl.close()` nor `child.stderr.removeAllListeners()` runs on exit. Leak is bounded (readline auto-closes when stdout emits end; `_child=null` makes refs GC-eligible) but defensive teardown also stops late stdout bytes from firing subscribers after exit.
- **Proposed fix:** In exit handler call `rl.close()` and `child.stderr.removeAllListeners()` before nulling `_child`.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] _readyReject never nulled after rejection permits double-reject
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 80% | **Verified:** PARTIAL
- **Evidence:** verbatim/engine-manager.js:149
- **Problem:** `_readyReject` is only cleared on successful resolve (L241). On error→exit both handlers call it; harmless today (Promise double-reject is noop) but latent risk if future refactor wires `_readyPromise` into a one-shot deferred or unhandled-rejection logger.
- **Proposed fix:** Null both `_readyResolve` and `_readyReject` after rejecting in the error handler (L139) and the ready-timeout handler (L162), matching the resolve path.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] extraResources: engine/ has no filter — untrimmed leak risk
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 80% | **Verified:** PARTIAL
- **Evidence:** verbatim/build-config/electron-builder.yml:44
- **Problem:** No `filter` on the extraResources entry. PyInstaller output normally omits pycache/pdb, but any stray dev artifact ships. Installer is already 2–4 GB; defensive filtering is cheap.
- **Proposed fix:** Add `filter: ['**/*', '!**/__pycache__', '!**/*.pyc', '!**/*.pdb', '!**/*.lib']`. Measure size delta.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] save-settings accepts any object — no schema validation
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** MED | **Effort:** LOW | **Confidence:** 78% | **Verified:** PARTIAL
- **Evidence:** verbatim/main.js:180
- **Problem:** Forwards any object straight to `JSON.stringify` → disk. A compromised renderer can stash attacker state (data_dir → UNC share) or write a multi-GB blob. `daemonEnv` only reads three keys, but schema evolution widens the surface. Verifier rejected the related pick-folder claim (user-driven dialog is safe).
- **Proposed fix:** Destructure + type-check only `{hf_token, anthropic_api_key, data_dir}` as strings; reject other keys; size-cap the payload. In daemonEnv verify `data_dir` is absolute and statable before setting `VERBATIM_ROOT`.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] Dead BatchView.tsx duplicates onEvent wiring
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** LOW | **Effort:** LOW | **Confidence:** 95% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/components/batch/BatchView.tsx:89
- **Problem:** Not imported anywhere. Duplicates `useBatchWorkspace` subscription logic. If someone later imports it alongside the hook, every daemon event fires two state updates on two parallel trees.
- **Proposed fix:** Delete `BatchView.tsx`.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

### [NEW] No engines / Node pin and no .nvmrc
- **Tool:** verbatim-electron
- **Source:** SMAC 2026-04-23
- **Impact:** LOW | **Effort:** LOW | **Confidence:** 90% | **Verified:** CONFIRMED
- **Evidence:** verbatim/package.json:28
- **Problem:** No `engines`, no `.nvmrc`, no `.npmrc engine-strict`. docs/packaging.md:31 says "Node 20+" in prose only. Caret on `electron ^41.0.0` floats Chromium majors — same app version could ship from Electron 41 or 42 on two dev boxes.
- **Proposed fix:** Add `"engines": { "node": ">=20.11" }`, drop `.nvmrc` at repo root, pin electron + electron-builder to exact versions.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-23-how-best-should-i-optimize.md`

## From SMAC 2026-04-24 (default optimization audit)

Full report: `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Successful polish drops original segment metadata
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 95% | **Verified:** CONFIRMED
- **Evidence:** persons/polish_engine.py:169
- **Problem:** Successful polish returns parsed LLM objects instead of copying originals, so speaker_name, speaker_role, speaker_confidence, matched_region, region, words, and cluster metadata can be lost before corpus/update stages.
- **Proposed fix:** After validate_chunk, copy each original segment and replace only text plus polish audit fields; never replace the whole segment with the LLM response.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Engine lock acquire is check-then-write, so two daemons can both pass startup
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 94% | **Verified:** CONFIRMED
- **Evidence:** utils/engine_lock.py:104
- **Problem:** `acquire()` reads existing JSON, then overwrites with a normal write. Two daemons can both see no live lock and both run writers against `_voiceprints` and corpus state.
- **Proposed fix:** Replace the JSON check-then-write with an OS file lock or atomic create with `O_CREAT|O_EXCL` plus a unique token, with stale-owner validation under the same primitive.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] file_complete failures normalize as success
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** HIGH | **Effort:** LOW | **Confidence:** 93% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/bridge/normalize.ts:491
- **Problem:** The daemon reports failures through `stats.ok`, but renderer normalization defaults any missing `state: 'failed'` to success. Failed or cancelled file_complete events can overwrite prior failed progress as success.
- **Proposed fix:** Normalize file_complete from explicit state first, then `stats.ok` when present; preserve stats and add tests for `stats.ok === false` and error-then-file_complete ordering.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] First-ever dual bootstrap can permanently swap teacher and student
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 92% | **Verified:** CONFIRMED
- **Evidence:** stage3_postprocess.py:77
- **Problem:** When both participants are new, orphan cluster labels come from an unordered set, then the first popped label becomes teacher and the next becomes student with bootstrap confidence 1.0.
- **Proposed fix:** Do not auto-bootstrap both missing roles from unordered orphan labels. Require manual confirmation or deterministic external mapping for dual-new sessions, with a regression test.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Diff-schema polish gates are implemented but not wired
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** HIGH | **Effort:** MED | **Confidence:** 92% | **Verified:** CONFIRMED
- **Evidence:** persons/polish_diff.py:32
- **Problem:** Deterministic patch gates for word confidence, phonetic similarity, and glossary corroboration exist but production still accepts full-segment LLM rewrites.
- **Proposed fix:** Switch polish_chunk_cli/api to request patch objects, pass glossary keys into `apply_patches`, then merge patched original segments instead of accepting rewritten segment objects.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Cancellation waits through whole threaded phase groups
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** MED | **Effort:** MED | **Confidence:** 86% | **Verified:** CONFIRMED
- **Evidence:** run.py:215
- **Problem:** `_process_one` checks cancellation before long synchronous bundles, then runs groups like `_finalize` in one worker thread. Cancellation during those groups waits until the whole bundle returns.
- **Proposed fix:** Split long worker bundles into per-phase awaits and call `cancellation.cancel_check()` between each phase; pass cancellation/timeout hooks into subprocess or model calls where possible.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Sung segments can fall back into speaking voice updates
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** MED | **Effort:** LOW | **Confidence:** 84% | **Verified:** CONFIRMED
- **Evidence:** stage3_postprocess.py:340
- **Problem:** Sung segments are remerged before voice-library update, and the update fallback ignores `seg['region']`, so sung audio can be accumulated as speaking when matched_region is missing.
- **Proposed fix:** In `update_voice_libraries`, skip `seg.get('sung')` or fall back to `seg.get('region')` before `speaking`; add a sung_low/sung_full regression test.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Collision detection ignores the same centroids used for matching
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** MED | **Effort:** LOW | **Confidence:** 84% | **Verified:** CONFIRMED
- **Evidence:** persons/matcher.py:150
- **Problem:** Matching scans every `.npy` centroid and recent-buffer row, but collision detection compares only `universal.npy`, so collisions in speaking/sung/recent vectors can be missed.
- **Proposed fix:** Extend collision sweeps to compare all matchable centroids with region names, at least same-region 1-D centroids plus recent rows, with shape validation before cosine.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Per-file await prevents CPU/GPU pipelining
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** HIGH | **Effort:** HIGH | **Confidence:** 88% | **Verified:** PARTIAL
- **Evidence:** run.py:421
- **Problem:** The normal driver awaits each file end-to-end. This serializes files, but verifier qualified that singleton model state makes staged overlap non-trivial.
- **Proposed fix:** Refactor into a bounded staged queue only after isolating singleton model state. Keep GPU users behind one semaphore, but overlap CPU-only decode/VAD and non-GPU polish/IO across files.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Batch footer ignores batch_started total
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** MED | **Effort:** MED | **Confidence:** 78% | **Verified:** CONFIRMED
- **Evidence:** verbatim/renderer/src/components/shell/BottomActionBar.tsx:65
- **Problem:** Footer progress divides by current UI selection, not daemon `batch_started.total`; redo and backend-filtered batches can show stale percentages or wrong totals.
- **Proposed fix:** Store `activeBatchTotal` from normalized `batch_started` in `useBatchWorkspace` and feed it to `BottomActionBar`; handle redo/file_started paths not present in files.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Word re-attribution launches one embedding call per word
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** MED | **Effort:** MED | **Confidence:** 84% | **Verified:** PARTIAL
- **Evidence:** utils/word_reattribute.py:97
- **Problem:** Every eligible spoken word window invokes the speaker embedder separately, creating many small model calls. Verifier qualified that sung, missing-word, and too-short windows are skipped.
- **Proposed fix:** Batch eligible word windows per file, or restrict re-attribution to boundary/low-confidence words before embedding.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Missing or malformed file_index mutates file zero
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** MED | **Effort:** LOW | **Confidence:** 82% | **Verified:** PARTIAL
- **Evidence:** verbatim/renderer/src/bridge/normalize.ts:445
- **Problem:** Missing or non-finite per-file indexes default to 0, so malformed payloads update the first row. Verifier qualified negative/fractional finite values as related validation gaps.
- **Proposed fix:** Require a non-negative integer `file_index`/`index` for per-file events; return null or route to a warning event when invalid, with tests for missing/negative/fractional indexes.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Cluster embedding time is reported as diarization
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** LOW | **Effort:** LOW | **Confidence:** 90% | **Verified:** CONFIRMED
- **Evidence:** run.py:273
- **Problem:** Cluster embedding runs inside the open diarization phase, so progress timings charge embedding/model work to diarization and hide the real cost center.
- **Proposed fix:** Add a separate embedding phase or move this timing into identification so reporter semantics match the work being measured.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Voice libraries are loaded twice per finalize before any mutation
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** LOW | **Effort:** LOW | **Confidence:** 90% | **Verified:** PARTIAL
- **Evidence:** stage3_postprocess.py:244
- **Problem:** `handle_sung_segments` and `reattribute_spoken_words` can rebuild the same person_id-to-library map before mutation. Verifier qualified that duplicate load happens only when sung segments are present.
- **Proposed fix:** Build one voice-library cache after identification and pass it into both sung handling and word re-attribution; invalidate only after `update_voice_libraries`.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`

### [NEW] Rejected command errors are emitted without the original command id
- **Tool:** smac
- **Source:** SMAC 2026-04-24
- **Impact:** LOW | **Effort:** LOW | **Confidence:** 80% | **Verified:** PARTIAL
- **Evidence:** engine_daemon.py:179
- **Problem:** Valid JSON rejection paths emit `ErrorEvent` without preserving a command id, so renderer-side request filters cannot correlate the rejection. Truly invalid JSON cannot reliably preserve an id.
- **Proposed fix:** Parse raw objects far enough to preserve `id` and `cmd` before validation; include id plus context on unknown_command and invalid_command_payload events when the raw payload was valid JSON.
- **Full report:** `~/Desktop/Claude/skills-archive/smac/runs/2026-04-24-how-best-should-i-optimize.md`
