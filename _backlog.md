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
